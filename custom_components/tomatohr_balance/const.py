"""Konstante integracije."""

from __future__ import annotations

DOMAIN = "tomatohr_balance"
API_BASE = "https://webauth.tomato.com.hr/mcrmtomato_oauth/api"
API_VERSION = "v4.6"
USER_AGENT = (
    "MojTomato/3.0.1 (co.infinum.mojtomato; build:3010000; type:release; "
    "os:Android 14; sdk:34) okhttp/4.12.0"
)
DEFAULT_SCAN_INTERVAL = 30  # minuta

CONF_MSISDN = "msisdn"
CONF_TAN = "tan"
