"""Tomato (HR) bonovi: stanje racuna kao Home Assistant integracija."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import e164
from .const import CONF_MSISDN, DOMAIN
from .coordinator import TomatoCoordinator

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

REDEEM_SCHEMA = vol.Schema(
    {
        vol.Required("code"): vol.All(str, vol.Length(min=8)),
        vol.Optional(CONF_MSISDN): str,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def async_redeem(call: ServiceCall) -> None:
        coordinators: dict[str, TomatoCoordinator] = hass.data.get(DOMAIN, {})
        if not coordinators:
            raise ServiceValidationError("Tomato integracija nema nijedan racun")
        if msisdn := call.data.get(CONF_MSISDN):
            wanted = e164(msisdn)
            coordinator = next((c for c in coordinators.values() if c.api.msisdn == wanted), None)
        elif len(coordinators) == 1:
            coordinator = next(iter(coordinators.values()))
        else:
            coordinator = None
        if coordinator is None:
            raise ServiceValidationError("Navedi msisdn (vise racuna)")
        await coordinator.api.async_top_up(call.data["code"])
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "redeem", async_redeem, schema=REDEEM_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = TomatoCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
