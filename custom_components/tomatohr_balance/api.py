"""Tanki async klijent za Moj Tomato API."""

from __future__ import annotations

import re
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import API_BASE, API_VERSION, USER_AGENT


class TomatoError(Exception):
    """Bazna greska."""


class TomatoAuthError(TomatoError):
    """Neispravni podaci, istekao token ili odbijen TAN."""


class TomatoApiError(TomatoError):
    """Neocekivan odgovor / mreza."""


def e164(raw: str) -> str:
    """0921234567 / +385 92... -> 385921234567."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        raise TomatoAuthError("Broj mobitela nije valjan")
    if not digits.startswith("385"):
        digits = "385" + digits[1:] if digits.startswith("0") else "385" + digits
    return digits


def walk_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_dicts(item)


def find_first(node: Any, key: str) -> Any:
    return next((d[key] for d in walk_dicts(node) if key in d), None)


def _parse_amount(value: Any) -> float | None:
    """Broj iz broja, dicta ({"value": ...}) ili stringa ("2,50 EUR")."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "amount", "formatted"):
            if key in value:
                return _parse_amount(value[key])
        return None
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:[.,]\d+)?", value.replace(" ", ""))
        if match:
            return float(match.group(0).replace(",", "."))
    return None


def tab_url(shell):
    """URL taba iz SDUI ljuske (content.tabBar.tabs[].url), ne pozadina/akcije."""
    tabs = ((shell or {}).get("content") or {}).get("tabBar", {}).get("tabs") or []
    for tab in tabs:
        url = tab.get("url")
        if url and "dashboard/tab" in url:
            return url
    for node in walk_dicts(shell):
        url = node.get("url")
        if isinstance(url, str) and "/tab/" in url:
            return url
    return None


def parse_balance(dashboard: Any) -> dict[str, Any] | None:
    """Prvi SDUI cvor s `currency` i iznosom = stanje racuna."""
    for node in walk_dicts(dashboard):
        currency = node.get("currency")
        if not currency:
            continue
        for key in ("amount", "price", "balance", "value"):
            if key in node:
                amount = _parse_amount(node[key])
                if amount is not None:
                    return {"amount": amount, "currency": currency}
    return None


class TomatoApi:
    """Jedan racun (MSISDN) i njegovi tokeni."""

    def __init__(
        self,
        session: ClientSession,
        msisdn: str,
        access: str | None = None,
        refresh: str | None = None,
        is_login_mfa: bool = False,
        on_tokens=None,
    ) -> None:
        self.session = session
        self.msisdn = e164(msisdn)
        self.access = access
        self.refresh_token = refresh
        self.is_login_mfa = is_login_mfa
        self._on_tokens = on_tokens

    async def _request(
        self, method: str, path: str, payload: dict | None = None, token: str | None = None
    ) -> Any:
        url = f"{API_BASE}/{path}"
        if "apiVersion" not in path:
            url += ("&" if "?" in path else "?") + f"apiVersion={API_VERSION}"
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT, "X-USER-AGENT": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with self.session.request(method, url, json=payload, headers=headers, timeout=30) as resp:
                body = await resp.text()
                if resp.status in (401, 403):
                    raise TomatoAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise TomatoApiError(f"HTTP {resp.status}: {body[:200]}")
        except ClientError as err:
            raise TomatoApiError(str(err)) from err
        try:
            import json

            return json.loads(body) if body.strip() else {}
        except ValueError as err:
            raise TomatoApiError(f"nije JSON: {body[:200]}") from err

    async def async_msisdn_login(self) -> dict[str, Any]:
        challenge = await self._request("POST", "token/msisdnLogin", {"msisdn": self.msisdn})
        if find_first(challenge, "transactionID") is None:
            raise TomatoAuthError("Broj nije povezan s Moj Tomato racunom")
        return challenge

    async def async_tan_login(self, challenge: dict[str, Any], tan: str) -> None:
        response = await self._request(
            "POST",
            "token/msisdnTanLogin",
            {
                "cookies": find_first(challenge, "cookies") or [],
                "tan": tan,
                "msisdn": self.msisdn,
                "transactionID": find_first(challenge, "transactionID"),
            },
        )
        self._store_tokens(response)

    async def async_refresh(self) -> None:
        if not self.refresh_token:
            raise TomatoAuthError("Nema refresh tokena")
        response = await self._request(
            "POST",
            "token/refresh",
            {"refreshToken": self.refresh_token, "isLoginMfa": self.is_login_mfa},
        )
        self._store_tokens(response)

    def _store_tokens(self, response: Any) -> None:
        tokens = find_first(response, "tokens")
        if not isinstance(tokens, dict) or not tokens.get("access"):
            raise TomatoAuthError("Odgovor nema tokene")
        self.access = tokens["access"]
        self.refresh_token = tokens.get("refresh") or self.refresh_token
        self.is_login_mfa = bool(tokens.get("isLoginMfa", self.is_login_mfa))
        if self._on_tokens:
            self._on_tokens(self.access, self.refresh_token, self.is_login_mfa)

    async def _get(self, path: str) -> Any:
        if not self.access:
            await self.async_refresh()
        try:
            return await self._request("GET", path, token=self.access)
        except TomatoAuthError:
            await self.async_refresh()
            return await self._request("GET", path, token=self.access)

    async def async_dashboard(self) -> dict[str, Any]:
        """Ljuska + sadrzaj odabranog taba (stanje je u tabu, ne u ljusci)."""
        shell = await self._get("dashboard")
        url = tab_url(shell)
        return {"shell": shell, "tab": await self._get(url) if url else shell}

    async def async_top_up(self, code: str) -> Any:
        return await self._request(
            "POST",
            "shop/topUpRenewal",
            {
                "token": re.sub(r"\D", "", code),
                "phoneNumber": self.msisdn,
                "inputMethod": "manual",
            },
            token=self.access,
        )
