"""Diagnostics: sirovi dashboard odgovor (za debug parsiranja)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MSISDN, DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "msisdn": entry.data.get(CONF_MSISDN),
        "dashboard": coordinator.data,
    }
