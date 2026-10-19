#!/usr/bin/env python3
"""Moj Tomato API klijent: bootstrap prijave (SMS TAN), stanje racuna i nadoplata bonom.

Endpointi i tokovi su rekonstruirani statickom analizom APK-a

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
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("TOMATO_API_BASE", "https://webauth.tomato.com.hr/mcrmtomato_oauth/api").rstrip("/")
API_VERSION = os.environ.get("TOMATO_API_VERSION", "v4.6")
STATE_PATH = Path(os.environ.get("TOMATO_STATE", "~/.config/tomato/state.json")).expanduser()
UA = (
    "MojTomato/3.0.1 (co.infinum.mojtomato; build:3010000; type:release; "
    "os:Android 14; sdk:34) okhttp/4.12.0"
)


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:400]}")
        self.status = status
        self.body = body


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
    if os.environ.get("TOMATO_FIREBASE_TOKEN"):
        headers["Firebase-Token"] = os.environ["TOMATO_FIREBASE_TOKEN"]
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


def find_first(node, key: str):
    """Prva vrijednost `key` bilo gdje u (SDUI) odgovoru."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = find_first(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_first(item, key)
            if found is not None:
                return found
    return None


def collect(node, keys: set[str], out: list[str], prefix: str = "") -> None:
    """Popis svih `keys` polja s putanjom -- dovoljno za SDUI bez poznate sheme."""
    if isinstance(node, dict):
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(value, (dict, list)):
                collect(value, keys, out, path)
            elif name in keys:
                out.append(f"{path} = {value}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            collect(item, keys, out, f"{prefix}[{i}]")


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


def cmd_refresh(_: argparse.Namespace) -> None:
    state = refresh_token(load_state())
    print(f"Access token osvjezen (msisdn {state.get('msisdn')}).")


def cmd_status(args: argparse.Namespace) -> None:
    dashboard = with_token("GET", "dashboard")
    if args.json:
        print(json.dumps(dashboard, ensure_ascii=False, indent=2))
        return
    lines: list[str] = []
    collect(
        dashboard,
        {
            "amount", "currency", "unit", "units", "name", "title", "label",
            "remaining", "price", "value", "consumption", "validUntil", "date",
        },
        lines,
    )
    if not lines:
        print("Odgovor nema prepoznatih polja; pokreni s --json za sirovi SDUI.")
    else:
        print("\n".join(dict.fromkeys(lines)))


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

    sub.add_parser("refresh", help="osvjezi access token").set_defaults(func=cmd_refresh)

    status = sub.add_parser("status", help="stanje racuna i preostalih jedinica")
    status.add_argument("--json", action="store_true", help="sirovi SDUI odgovor")
    status.set_defaults(func=cmd_status)

    redeem = sub.add_parser("redeem", help="nadoplati racun kodom bona")
    redeem.add_argument("--code", required=True, help="14-znamenkasti kod s bona")
    redeem.add_argument("--msisdn", help="broj koji se nadoplacuje (default iz prijave)")
    redeem.set_defaults(func=cmd_redeem)

    args = parser.parse_args()
    try:
        args.func(args)
    except ApiError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
