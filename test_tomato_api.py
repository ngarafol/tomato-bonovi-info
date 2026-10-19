import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("tomato_api", Path(__file__).with_name("tomato_api.py"))
tomato = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tomato)


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

    def test_collect_flattens_with_paths(self):
        lines = []
        tomato.collect(self.dashboard, {"amount", "currency", "name"}, lines)
        self.assertIn("content[0].price.amount = 7.42", lines)
        self.assertIn("content[1].units[0].name = MIN", lines)

    def test_tokens_from_wrapped_response(self):
        response = {"state": "success", "data": {"tokens": {"access": "a", "refresh": "r", "isLoginMfa": False}}}
        self.assertEqual(tomato.tokens_from(response)["refresh"], "r")
        self.assertIsNone(tomato.tokens_from({"state": "invalidCode"}))


if __name__ == "__main__":
    unittest.main()
