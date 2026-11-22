"""Config flow: broj + SMS TAN (jednokratno)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TomatoApi, TomatoApiError, TomatoAuthError, e164
from .const import CONF_MSISDN, CONF_TAN, DOMAIN


class TomatoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Jedan racun po MSISDN-u."""

    VERSION = 1

    def __init__(self) -> None:
        self._challenge: dict[str, Any] | None = None
        self._msisdn: str = ""
        self._api: TomatoApi | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._msisdn = e164(user_input[CONF_MSISDN])
                self._api = TomatoApi(async_get_clientsession(self.hass), self._msisdn)
                self._challenge = await self._api.async_msisdn_login()
            except TomatoAuthError:
                errors["base"] = "no_account"
            except TomatoApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(self._msisdn)
                self._abort_if_unique_id_configured()
                return await self.async_step_tan()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MSISDN): str}),
            errors=errors,
        )

    async def async_step_tan(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        assert self._api is not None and self._challenge is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._api.async_tan_login(self._challenge, user_input[CONF_TAN])
            except TomatoAuthError:
                errors["base"] = "invalid_tan"
            except TomatoApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=self._msisdn,
                    data={
                        CONF_MSISDN: self._msisdn,
                        "access": self._api.access,
                        "refresh": self._api.refresh_token,
                        "is_login_mfa": self._api.is_login_mfa,
                    },
                )

        return self.async_show_form(
            step_id="tan",
            data_schema=vol.Schema({vol.Required(CONF_TAN): str}),
            errors=errors,
        )
