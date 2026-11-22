"""Senzor stanja racuna."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import parse_dashboard
from .const import CONF_MSISDN, DOMAIN
from .coordinator import TomatoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TomatoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TomatoBalanceSensor(coordinator, entry)])


class TomatoBalanceSensor(CoordinatorEntity[TomatoCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True
    _attr_name = "Stanje"
    _attr_icon = "mdi:wallet"

    def __init__(self, coordinator: TomatoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_balance"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Tomato",
            "model": "Bonovi",
            "name": f"Tomato {entry.data[CONF_MSISDN]}",
        }

    @property
    def native_value(self) -> float | None:
        return parse_dashboard(self.coordinator.data).get("balance")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = parse_dashboard(self.coordinator.data)
        attrs: dict[str, Any] = {"msisdn": self.coordinator.entry.data[CONF_MSISDN]}
        for key in ("currency", "units", "tariff", "tariff_valid_until", "account_valid_until"):
            if info.get(key) is not None:
                attrs[key] = info[key]
        return attrs
