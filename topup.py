#!/usr/bin/env python3
"""Tomato bonovi s distance: pregled, provjera broja i kupnja bona karticom.

Koristi javni webshop API (services.tomato.com.hr/vouchers) koji poziva i sam
web na https://www.tomato.com.hr/bonovi. Ne treba Tomato SIM, aplikacija ni
prijava -- samo broj mobitela i kartica u pregledniku.

Primjeri:
    ./topup.py list
    ./topup.py check --msisdn 0921234567
    ./topup.py buy --msisdn 0921234567 --amount 16 --email ja@example.com
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE = os.environ.get("TOMATO_VOUCHERS_BASE", "https://services.tomato.com.hr/vouchers")
# Javni kljuc webshop klijenta (isti string je u /client-extensions/vouchers/voucher.js).
API_KEY = os.environ.get("TOMATO_API_KEY", "DYsoiLt9ihxunUMAmU9XebbqdqKcYW6dXs")


def call(method: str, path: str, payload: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={
            "TOMATO-API-KEY": API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code}: {exc.read().decode()[:300]}")
    return json.loads(body) if body.strip() else None


def e164(raw: str, plus: bool = False) -> str:
    """0921234567 / +385 92... -> 385921234567 (ili +385921234567)."""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        sys.exit("Broj mobitela nije valjan.")
    if not digits.startswith("385"):
        digits = "385" + digits[1:] if digits.startswith("0") else "385" + digits
    return ("+" if plus else "") + digits


def cmd_list(_: argparse.Namespace) -> None:
    data = call("GET", "/vouchers")
    for v in data["voucherList"]:
        price = "varijabilno" if v.get("custom") else f"{v['price']} EUR"
        print(f"{v['sapMm']:>12}  {price:<12} {v['promotion']}")
    print(f"\nRaspon: {data['minValue']}-{data['maxValue']} EUR")


def cmd_check(args: argparse.Namespace) -> None:
    print(json.dumps(call("POST", "/validate/phone-number", {"msisdn": e164(args.msisdn)}), ensure_ascii=False))


def pick_voucher(msisdn: str, amount: float) -> tuple[str, float | None]:
    data = call("GET", "/vouchers")
    for v in data["voucherList"]:
        if not v.get("custom") and float(v["price"]) == amount:
            return v["sapMm"], None
    custom = next((v for v in data["voucherList"] if v.get("custom")), None)
    if custom and data["minValue"] <= amount <= data["maxValue"]:
        return custom["sapMm"], amount
    sys.exit(f"Iznos {amount} EUR nije podrzan (fiksni bonovi ili {data['minValue']}-{data['maxValue']} EUR).")


def cmd_buy(args: argparse.Namespace) -> None:
    msisdn = e164(args.msisdn)
    sap_mm, free_entry = pick_voucher(msisdn, args.amount)
    body = {
        "sapMm": sap_mm,
        "customerData": {"phoneNumber": "+" + msisdn, "email": args.email},
    }
    if free_entry is not None:
        body["freeEntryValue"] = free_entry
    if args.company:
        name, oib, address, postal, city = args.company
        body["companyData"] = {"name": name, "oib": oib, "address": address, "postalCode": postal, "city": city}

    order = call("POST", "/purchase-voucher", body)
    link, params = order["redirectLink"], order.get("paymentGatewayParameters") or {}
    print(f"Narudzba: {args.amount:g} EUR za +{msisdn}\nNaplata: {link}")

    hidden = "\n".join(
        f'<input type="hidden" name="{k}" value="{str(v)}">' for k, v in params.items()
    )
    page = Path("payment.html").resolve()
    page.write_text(
        f'<form method="post" action="{link}">{hidden}</form>'
        "<script>document.forms[0].submit()</script>",
        encoding="utf-8",
    )
    print(f"Placanje spremno u: {page}")
    if args.open:
        webbrowser.open(page.as_uri())


def main() -> None:
    parser = argparse.ArgumentParser(description="Tomato bonovi s distance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="popis bonova i promocija").set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="je li broj Tomato (bez kupnje)")
    check.add_argument("--msisdn", required=True)
    check.set_defaults(func=cmd_check)

    buy = sub.add_parser("buy", help="kupi bon i pripremi placanje karticom")
    buy.add_argument("--msisdn", required=True, help="broj koji se nadoplacuje")
    buy.add_argument("--amount", type=float, required=True, help="iznos u EUR")
    buy.add_argument("--email", default="", help="e-mail za potvrdu")
    buy.add_argument("--company", nargs=5, metavar=("NAZIV", "OIB", "ADRESA", "POSTANSKI", "GRAD"))
    buy.add_argument("--open", action="store_true", help="odmah otvori placanje u pregledniku")
    buy.set_defaults(func=cmd_buy)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
