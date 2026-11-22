import contextlib
import io
import sys
import unittest
from datetime import date

import tomato_api as tomato


class TestNormalize(unittest.TestCase):
    def test_e164(self):
        for raw in ("0921234567", "+385 92 123 4567", "385921234567", "0 92/123-4567"):
            self.assertEqual(tomato.e164(raw), "385921234567")

    def test_url_for_adds_api_version_once(self):
        self.assertTrue(tomato.url_for("dashboard").endswith("/dashboard?apiVersion=v4.6"))
        self.assertTrue(tomato.url_for("token/refresh?apiVersion=v4.6").endswith("/token/refresh?apiVersion=v4.6"))


class TestSdui(unittest.TestCase):
    dashboard = {
        "content": [
            {"type": "accountInfoCard", "price": {"amount": "7.42", "currency": "EUR"}},
            {"type": "unitsStatus", "units": [{"name": "MIN", "amount": 120}]},
        ]
    }

    def test_find_first_goes_through_lists(self):
        self.assertEqual(tomato.find_first(self.dashboard, "currency"), "EUR")
        self.assertIsNone(tomato.find_first(self.dashboard, "nema-me"))

    def test_tokens_from_wrapped_response(self):
        response = {"state": "success", "data": {"tokens": {"access": "a", "refresh": "r", "isLoginMfa": False}}}
        self.assertEqual(tomato.tokens_from(response)["refresh"], "r")
        self.assertIsNone(tomato.tokens_from({"state": "invalidCode"}))

    def test_parse_balance_ignores_other_amounts(self):
        self.assertEqual(tomato.parse_balance(self.dashboard)["amount"], 7.42)
        self.assertEqual(tomato.parse_balance(self.dashboard)["currency"], "EUR")
        self.assertIsNone(tomato.parse_balance({"content": [{"amount": "120"}]}))

    def test_parse_balance_accepts_comma_decimals(self):
        self.assertEqual(tomato.parse_balance({"price": {"amount": "7,42", "currency": "EUR"}})["amount"], 7.42)

    def test_parse_balance_nested_and_string_amounts(self):
        self.assertEqual(
            tomato.parse_balance({"account": {"balance": {"value": "7,42"}, "currency": "EUR"}})["amount"], 7.42
        )
        self.assertEqual(
            tomato.parse_balance({"amount": "2,50 EUR", "currency": "EUR"})["amount"], 2.5
        )

    def test_tab_url_ignores_background_and_actions(self):
        shell = {
            "background": {"type": "image", "url": "https://ssc.a1.hr/bg.png"},
            "content": {"tabBar": {"tabs": [
                {"label": {"text": "Tomato"}, "url": "dashboard/tab/myDashboard?apiVersion=v4.6"}
            ]}},
            "rightActions": [{"action": {"url": "settings/settingsScreen?apiVersion=v4.6"}}],
        }
        self.assertEqual(tomato.tab_url(shell), "dashboard/tab/myDashboard?apiVersion=v4.6")
        self.assertIsNone(tomato.tab_url({"background": {"url": "https://x/y.png"}}))

    real_tab = {
        "shell": {"title": {"text": "098 000 000"}},
        "tab": {
            "components": [
                {
                    "componentType": "accountInfoCard",
                    "price": {"primaryPrice": {"amount": "10,82", "unit": "€", "style": "H1"}},
                    "body": {"text": "Racun istice 16.02.2027."},
                },
                {
                    "componentType": "animatedInfoCard",
                    "title": {"text": "OPTI MALA"},
                    "body": {"text": "Tarifa istjece 04.12.2026."},
                },
                {
                    "componentType": "unlimitedUnitItem",
                    "description": {"value": {"text": "7956"}, "total": {"text": "jedinica"}},
                    "caption": {"text": "Traje do 04.12.2026."},
                },
            ]
        },
    }

    def test_parse_dashboard_real_shape(self):
        info = tomato.parse_dashboard(self.real_tab)
        self.assertEqual(info["balance"], 10.82)
        self.assertEqual(info["currency"], "EUR")
        self.assertEqual(info["units"]["value"], 7956)
        self.assertEqual(info["units"]["label"], "jedinica")
        self.assertEqual(info["tariff"], "OPTI MALA")
        self.assertEqual(info["tariff_valid_until"], "04.12.2026")
        self.assertEqual(info["account_valid_until"], "16.02.2027")

    def test_parse_dashboard_falls_back_to_generic_parser(self):
        payload = {"tab": {"components": []}, "balance": {"amount": "3,50", "currency": "EUR"}}
        self.assertEqual(tomato.parse_dashboard(payload)["balance"], 3.5)

    def test_to_date(self):
        self.assertEqual(tomato.to_date("04.12.2026"), date(2026, 12, 4))
        self.assertIsNone(tomato.to_date(None))
        self.assertIsNone(tomato.to_date("nema datuma"))


class TestNotify(unittest.TestCase):
    def test_dry_run_escapes_quotes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tomato.notify('Tomato "test"', "1.00 EUR", dry_run=True)
        self.assertNotIn('"test"', out.getvalue())
        if sys.platform == "darwin":
            self.assertIn("osascript", out.getvalue())


if __name__ == "__main__":
    unittest.main()
