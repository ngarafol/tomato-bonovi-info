"""Testovi za integracijski API klijent, bez Home Assistant-a.

api.py se učitava direktno (zaobilazi __init__.py koji trazi homeassistant),
pa je dovoljan aiohttp.
"""

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

PATH = pathlib.Path(__file__).parent / "custom_components" / "tomatohr_balance"


def load_api():
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return None
    package = types.ModuleType("tomatohr_balance")
    package.__path__ = [str(PATH)]
    sys.modules["tomatohr_balance"] = package
    spec = importlib.util.spec_from_file_location("tomatohr_balance.api", PATH / "api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["tomatohr_balance.api"] = module
    spec.loader.exec_module(module)
    return module


API = load_api()


@unittest.skipUnless(API, "aiohttp nije instaliran")
class TestTokenRefresh(unittest.IsolatedAsyncioTestCase):
    def make_api(self):
        api = API.TomatoApi(object(), "385921234567", access="old", refresh="r1")

        async def fake_request(method, path, payload=None, token=None):
            if token == "old":
                raise API.TomatoAuthError("HTTP 401: expired")
            return {"ok": True}

        async def fake_refresh():
            await asyncio.sleep(0.01)
            api.access = "new"

        api._request = fake_request
        api.async_refresh = fake_refresh
        return api

    async def test_parallel_401_refreshes_only_once(self):
        api = self.make_api()
        refresh_calls = 0
        base_refresh = api.async_refresh

        async def counting_refresh():
            nonlocal refresh_calls
            refresh_calls += 1
            await base_refresh()

        api.async_refresh = counting_refresh
        results = await asyncio.gather(api._get("dashboard"), api._get("dashboard"))
        self.assertEqual(refresh_calls, 1)
        self.assertTrue(all(result["ok"] for result in results))

    async def test_top_up_retries_after_401(self):
        api = self.make_api()
        self.assertEqual(await api.async_top_up("12345678901234"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
