"""Koordinacija osvjezavanja stanja."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TomatoApi, TomatoApiError, TomatoAuthError
from .const import CONF_MSISDN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TomatoCoordinator(DataUpdateCoordinator[Any]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_MSISDN]}",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.api = TomatoApi(
            async_get_clientsession(hass),
            entry.data[CONF_MSISDN],
            entry.data.get("access"),
            entry.data.get("refresh"),
            entry.data.get("is_login_mfa", False),
            on_tokens=self._persist_tokens,
        )

    def _persist_tokens(self, access: str, refresh: str | None, is_login_mfa: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                "access": access,
                "refresh": refresh,
                "is_login_mfa": is_login_mfa,
            },
        )

    async def _async_update_data(self) -> Any:
        try:
            return await self.api.async_dashboard()
        except TomatoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TomatoApiError as err:
            raise UpdateFailed(str(err)) from err
