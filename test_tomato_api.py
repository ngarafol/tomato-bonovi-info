import contextlib
import io
import sys
import unittest

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
