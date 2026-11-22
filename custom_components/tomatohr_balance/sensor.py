"""Senzori: stanje, jedinice i tarifa."""

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

from .api import parse_dashboard, to_date
from .const import CONF_MSISDN, DOMAIN
from .coordinator import TomatoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TomatoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TomatoBalanceSensor(coordinator, entry),
            TomatoUnitsSensor(coordinator, entry),
            TomatoTariffSensor(coordinator, entry),
        ]
    )


class TomatoSensor(CoordinatorEntity[TomatoCoordinator], SensorEntity):
    """Zajednicki dio: uredjaj, unique_id i parsirani dashboard."""

    _attr_has_entity_name = True
    _entity_key = "sensor"

    def __init__(self, coordinator: TomatoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{self._entity_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Tomato",
            "model": "Bonovi",
            "name": f"Tomato {entry.data[CONF_MSISDN]}",
        }

    @property
    def info(self) -> dict[str, Any]:
        return parse_dashboard(self.coordinator.data)


class TomatoBalanceSensor(TomatoSensor):
    _entity_key = "balance"
    _attr_name = "Stanje"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:wallet"

    @property
    def native_value(self) -> float | None:
        return self.info.get("balance")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "msisdn": self.coordinator.entry.data[CONF_MSISDN],
            "currency": self.info.get("currency") or "EUR",
            "account_valid_until": to_date(self.info.get("account_valid_until")),
        }


class TomatoUnitsSensor(TomatoSensor):
    _entity_key = "units"
    _attr_name = "Jedinice"
    _attr_native_unit_of_measurement = "jedinica"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    @property
    def native_value(self) -> float | None:
        return (self.info.get("units") or {}).get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        units = self.info.get("units") or {}
        return {
            "label": units.get("label"),
            "valid_until": to_date(units.get("valid_until")),
        }


class TomatoTariffSensor(TomatoSensor):
    _entity_key = "tariff"
    _attr_name = "Tarifa"
    _attr_icon = "mdi:card-account-details-outline"

    @property
    def native_value(self) -> str | None:
        return self.info.get("tariff")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"valid_until": to_date(self.info.get("tariff_valid_until"))}
