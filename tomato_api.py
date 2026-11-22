#!/usr/bin/env python3
"""Moj Tomato API klijent: bootstrap prijave (SMS TAN), stanje racuna i nadoplata bonom.

Endpointi su rekonstruirani iz APK-a `co.infinum.mojtomato` 3.0.1.

Prvi token se ne moze dobiti bez SIM-a/mobitela: prijava `token/msisdnLogin`
salje SMS TAN na broj. Nakon tog jednog koraka sve dalje radi s bilo koje mreze
jer `token/refresh` trazi samo refresh token.

    ./tomato_api.py login --msisdn 0921234567   # posalje TAN, ti upises kod
    ./tomato_api.py status
    ./tomato_api.py status --json
    ./tomato_api.py redeem --code 12345678901234

Automatizirano koristenje API-ja gotovo sigurno krsi uvjete koristenja Tomato/A1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("TOMATO_API_BASE", "https://webauth.tomato.com.hr/mcrmtomato_oauth/api").rstrip("/")
API_VERSION = "v4.6"
STATE_PATH = Path(os.environ.get("TOMATO_STATE", "~/.config/tomato/state.json")).expanduser()
UA = (
    "MojTomato/3.0.1 (co.infinum.mojtomato; build:3010000; type:release; "
    "os:Android 14; sdk:34) okhttp/4.12.0"
)


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:400]}")
        self.status = status


def e164(raw: str) -> str:
    """0921234567 -> 385921234567 (bez plusa, kako salje aplikacija)."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        sys.exit("Broj mobitela nije valjan.")
    if not digits.startswith("385"):
        digits = "385" + digits[1:] if digits.startswith("0") else "385" + digits
    return digits


def url_for(path: str) -> str:
    if "apiVersion" in path:
        return f"{BASE}/{path.lstrip('/')}"
    sep = "&" if "?" in path else "?"
    return f"{BASE}/{path.lstrip('/')}{sep}apiVersion={API_VERSION}"


def request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    headers = {"Accept": "application/json", "User-Agent": UA, "X-USER-AGENT": UA}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url_for(path), method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode(errors="replace")) from None
    try:
        return json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        raise ApiError(200, f"nije JSON: {body[:200]}") from None


def walk_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_dicts(item)


def find_first(node, key: str):
    """Prva vrijednost `key` bilo gdje u (SDUI) odgovoru."""
    return next((d[key] for d in walk_dicts(node) if key in d), None)


def _parse_amount(value) -> float | None:
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


def parse_balance(dashboard: dict) -> dict | None:
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


def notify(title: str, message: str, dry_run: bool = False) -> None:
    title, message = title.replace('"', "'"), message.replace('"', "'")
    command = None
    if sys.platform == "darwin":
        command = ["osascript", "-e", f'display notification "{message}" with title "{title}"']
    elif shutil.which("notify-send"):
        command = ["notify-send", title, message]
    if command is None:
        print(f"[obavijest] {title}: {message}")
        return
    if dry_run:
        print("[dry-run] " + " ".join(command))
        return
    subprocess.run(command, check=False)


# --- state / tokeni -------------------------------------------------------

def load_state() -> dict:
    if not STATE_PATH.exists():
        sys.exit(f"Nema spremljenih tokena ({STATE_PATH}). Prvo: login --msisdn <broj>")
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    STATE_PATH.chmod(0o600)


def tokens_from(response: dict) -> dict | None:
    tokens = find_first(response, "tokens")
    if isinstance(tokens, dict) and tokens.get("access"):
        return {
            "access": tokens["access"],
            "refresh": tokens.get("refresh"),
            "isLoginMfa": bool(tokens.get("isLoginMfa")),
            "msisdn": find_first(response, "msisdn"),
        }
    return None


def refresh_token(state: dict) -> dict:
    response = request(
        "POST",
        "token/refresh",
        {"refreshToken": state["refresh"], "isLoginMfa": bool(state.get("isLoginMfa"))},
    )
    refreshed = tokens_from(response) or {}
    state.update({k: v for k, v in refreshed.items() if v is not None})
    if not state.get("access"):
        raise ApiError(200, f"refresh nije vratio access token: {json.dumps(response)[:200]}")
    save_state(state)
    return state


def with_token(method: str, path: str, payload: dict | None = None) -> dict:
    """Poziv s access tokenom; na 401 jednom osvjezi token (kao TokenAuthenticator)."""
    state = load_state()
    try:
        return request(method, path, payload, token=state["access"])
    except ApiError as exc:
        if exc.status != 401:
            raise
    state = refresh_token(state)
    return request(method, path, payload, token=state["access"])


# --- naredbe --------------------------------------------------------------

def cmd_login(args: argparse.Namespace) -> None:
    if args.username:
        password = args.password
        if not password:
            import getpass

            password = getpass.getpass("Lozinka: ")
        challenge = request("POST", "token/mfaLogin", {"username": args.username, "password": password})
        step = "token/mfaTanLogin"
    else:
        if not args.msisdn:
            sys.exit("Daj --msisdn ili --username.")
        challenge = request("POST", "token/msisdnLogin", {"msisdn": e164(args.msisdn)})
        step = "token/msisdnTanLogin"

    print("Izazov:", json.dumps(challenge, ensure_ascii=False)[:300])
    if find_first(challenge, "transactionID") is None and not find_first(challenge, "tokens"):
        sys.exit("Server nije vratio izazov s TAN-om (je li broj povezan s Moj Tomato racunom?).")

    tan = args.tan or input("TAN iz SMS-a: ").strip()
    if not tan:
        sys.exit("Bez TAN-a nema prijave.")

    payload = {
        "cookies": find_first(challenge, "cookies") or [],
        "tan": tan,
        "msisdn": e164(args.msisdn) if args.msisdn else None,
        "transactionID": find_first(challenge, "transactionID"),
    }
    response = request("POST", step, payload)
    tokens = tokens_from(response)
    if not tokens:
        sys.exit(f"TAN nije prihvacen ili odgovor nije prepoznat: {json.dumps(response, ensure_ascii=False)[:400]}")
    if args.msisdn:
        tokens["msisdn"] = tokens.get("msisdn") or e164(args.msisdn)
    save_state(tokens)
    print(f"Prijava OK za {tokens['msisdn']}. Tokeni u {STATE_PATH} (0600).")


def fetch_dashboard() -> dict:
    shell = with_token("GET", "dashboard")
    url = tab_url(shell)
    return {"shell": shell, "tab": with_token("GET", url) if url else shell}


def cmd_status(args: argparse.Namespace) -> None:
    dashboard = fetch_dashboard()
    if args.json:
        print(json.dumps(dashboard, ensure_ascii=False, indent=2))
        return
    info = parse_dashboard(dashboard)
    if "balance" not in info:
        print("Ne mogu prepoznati stanje; pokreni s --json za sirovi SDUI.")
        return
    print(f"Stanje: {info['balance']:.2f} {info.get('currency') or 'EUR'}")
    units = info.get("units")
    if units:
        expiry = f" (do {units['valid_until']})" if units.get("valid_until") else ""
        print(f"Jedinice: {units['value']:g} {units.get('label') or ''}{expiry}")
    if info.get("tariff"):
        expiry = f" (do {info['tariff_valid_until']})" if info.get("tariff_valid_until") else ""
        print(f"Tarifa: {info['tariff']}{expiry}")
    if info.get("account_valid_until"):
        print(f"Racun istjece: {info['account_valid_until']}")


def cmd_balance(_: argparse.Namespace) -> None:
    """Strojno citljiv izlaz za Home Assistant / skripte."""
    info = parse_dashboard(fetch_dashboard())
    if "balance" not in info:
        sys.exit("Ne mogu prepoznati stanje u dashboardu; pokreni status --json.")
    print(json.dumps({"amount": info["balance"], "currency": info.get("currency") or "EUR"}, ensure_ascii=False))


def cmd_watch(args: argparse.Namespace) -> None:
    while True:
        dashboard = fetch_dashboard()
        info = parse_dashboard(dashboard)
        if "balance" not in info:
            sys.exit("Ne mogu prepoznati stanje u dashboardu; pokreni status --json i javi mi strukturu.")

        state = load_state()
        below = info["balance"] < args.below
        send = below and not state.get("alerted", False)
        state["alerted"] = below
        save_state(state)
        stamp = time.strftime("%Y-%m-%d %H:%M")
        print(f"{stamp}  {info['balance']:.2f} {info.get('currency') or 'EUR'}  (prag {args.below:g})")

        if send:
            notify(
                "Tomato: nisko stanje",
                f"{info['balance']:.2f} {info.get('currency') or 'EUR'} (prag {args.below:g})",
                dry_run=args.dry_run,
            )
        if not args.every:
            return
        time.sleep(args.every)


def cmd_redeem(args: argparse.Namespace) -> None:
    code = re.sub(r"\D", "", args.code)
    msisdn = e164(args.msisdn) if args.msisdn else load_state().get("msisdn")
    if not msisdn:
        sys.exit("Nemam broj (dodaj --msisdn).")
    response = with_token(
        "POST", "shop/topUpRenewal", {"token": code, "phoneNumber": msisdn, "inputMethod": "manual"}
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Moj Tomato API (stanje i nadoplata)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    login = sub.add_parser("login", help="prijava uz SMS TAN (jednokratni bootstrap)")
    login.add_argument("--msisdn", help="Tomato broj (prijava brojem)")
    login.add_argument("--username", help="korisnicko ime, ako broj nema racun")
    login.add_argument("--password", help="lozinka (inace se pita)")
    login.add_argument("--tan", help="TAN (ako ga vec imas; inace se pita)")
    login.set_defaults(func=cmd_login)

    status = sub.add_parser("status", help="stanje racuna i preostalih jedinica")
    status.add_argument("--json", action="store_true", help="sirovi SDUI odgovor")
    status.set_defaults(func=cmd_status)

    sub.add_parser("balance", help="stanje kao JSON (za Home Assistant)").set_defaults(func=cmd_balance)

    watch = sub.add_parser("watch", help="obavijest kad stanje padne pod prag")
    watch.add_argument("--below", type=float, required=True, help="prag u EUR")
    watch.add_argument("--every", type=int, help="sekunde izmedu provjera (default: samo jednom)")
    watch.add_argument("--dry-run", action="store_true", help="prikazi naredbu umjesto obavijesti")
    watch.set_defaults(func=cmd_watch)

    redeem = sub.add_parser("redeem", help="nadoplati racun kodom bona")
    redeem.add_argument("--code", required=True, help="14-znamenkasti kod s bona")
    redeem.add_argument("--msisdn", help="broj koji se nadoplacuje (default iz prijave)")
    redeem.set_defaults(func=cmd_redeem)

    args = parser.parse_args()
    try:
        args.func(args)
    except ApiError as exc:
        sys.exit(str(exc))


DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")


def _to_number(text) -> float | None:
    raw = str(text).strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(match.group(0)) if match else None


def _first_date(text) -> str | None:
    match = DATE_RE.search(str(text or ""))
    return match.group(0) if match else None


def parse_dashboard(payload) -> dict:
    """Iz SDUI taba izvuci stanje, jedinice i tarifu."""
    tab = payload.get("tab", payload) if isinstance(payload, dict) else {}
    info: dict = {}
    for comp in (tab or {}).get("components") or []:
        ctype = comp.get("componentType")
        if ctype in ("accountInfoCard", "highlightedAmountCard"):
            price = (comp.get("price") or {}).get("primaryPrice") or {}
            amount = _to_number(price.get("amount"))
            if amount is not None:
                info["balance"] = amount
                info["currency"] = "EUR" if price.get("unit") in ("\u20ac", "EUR") else price.get("unit")
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


if __name__ == "__main__":
    main()
