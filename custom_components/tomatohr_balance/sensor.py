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

from .api import find_first, parse_balance
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
        balance = parse_balance(self.coordinator.data)
        return balance["amount"] if balance else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        units = find_first(self.coordinator.data, "units")
        return {
            "msisdn": self.coordinator.entry.data[CONF_MSISDN],
            "units": units if isinstance(units, list) else [],
        }
