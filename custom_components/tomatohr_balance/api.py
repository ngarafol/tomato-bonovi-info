"""Tanki async klijent za Moj Tomato API."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
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
        return _to_number(value)
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
        self._refresh_lock = asyncio.Lock()

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
                    raise TomatoAuthError(f"HTTP {resp.status}: {body[:300]}")
                if resp.status >= 400:
                    raise TomatoApiError(f"HTTP {resp.status}: {body[:200]}")
        except ClientError as err:
            raise TomatoApiError(str(err)) from err
        try:
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

    async def _refresh_shared(self, used_access: str | None) -> None:
        """Osvjezi token samo ako ga druga zadaca vec nije osvjezila (rotirajuci refresh tokeni)."""
        async with self._refresh_lock:
            if used_access is not None and self.access != used_access:
                return
            await self.async_refresh()

    async def _authed(self, method: str, path: str, payload: dict | None = None) -> Any:
        if not self.access:
            await self._refresh_shared(None)
        used = self.access
        try:
            return await self._request(method, path, payload, token=used)
        except TomatoAuthError:
            await self._refresh_shared(used)
            return await self._request(method, path, payload, token=self.access)

    async def async_dashboard(self) -> dict[str, Any]:
        """Ljuska + sadrzaj odabranog taba (stanje je u tabu, ne u ljusci)."""
        shell = await self._authed("GET", "dashboard")
        url = tab_url(shell)
        return {"shell": shell, "tab": await self._authed("GET", url) if url else shell}

    async def async_top_up(self, code: str) -> Any:
        return await self._authed(
            "POST",
            "shop/topUpRenewal",
            {
                "token": re.sub(r"\D", "", code),
                "phoneNumber": self.msisdn,
                "inputMethod": "manual",
            },
        )


DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")


def _to_number(text: Any) -> float | None:
    """'10,82' / '1.234,56' / '7956' -> broj."""
    raw = str(text).strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(match.group(0)) if match else None


def _first_date(text: Any) -> str | None:
    match = DATE_RE.search(str(text or ""))
    return match.group(0) if match else None


def parse_dashboard(payload: Any) -> dict[str, Any]:
    """Iz SDUI taba izvuci stanje, jedinice i tarifu (accountInfoCard i dr.)."""
    tab = payload.get("tab", payload) if isinstance(payload, dict) else {}
    info: dict[str, Any] = {}
    for comp in (tab or {}).get("components") or []:
        ctype = comp.get("componentType")
        if ctype in ("accountInfoCard", "highlightedAmountCard"):
            price = (comp.get("price") or {}).get("primaryPrice") or {}
            amount = _to_number(price.get("amount"))
            if amount is not None:
                info["balance"] = amount
                info["currency"] = "EUR" if price.get("unit") in ("€", "EUR") else price.get("unit")
            info["account_valid_until"] = _first_date((comp.get("body") or {}).get("text"))
        elif ctype in ("unlimitedUnitItem", "unitItem"):
            description = comp.get("description") or {}
            value = (description.get("value") or {}).get("text")
            if value is not None:
                info["units"] = {
                    "value": _to_number(value),
                    "label": (description.get("total") or {}).get("text"),
                    "valid_until": _first_date((comp.get("caption") or {}).get("text")),
                }
        elif ctype == "animatedInfoCard":
            info["tariff"] = (comp.get("title") or {}).get("text")
            info["tariff_valid_until"] = _first_date((comp.get("body") or {}).get("text"))

    if "balance" not in info:
        fallback = parse_balance(payload)
        if fallback:
            info.update(balance=fallback["amount"], currency=fallback["currency"])
    return info

def to_date(text) -> "date | None":
    """'04.12.2026' -> date(2026, 12, 4); neispravno -> None."""
    try:
        day, month, year = str(text).split(".")
        return date(int(year), int(month), int(day))
    except (AttributeError, TypeError, ValueError):
        return None
