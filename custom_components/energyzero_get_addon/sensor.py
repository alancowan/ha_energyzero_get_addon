"""Price sensors for the Energy Zero Get Addon integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import AddonConfigEntry
from .const import ATTR_PRICES_TODAY, ATTR_PRICES_TOMORROW, PriceType
from .coordinator import PriceCoordinator, PricePoint, current_point
from .entity import AddonEntity

UNITS = {
    PriceType.ELECTRICITY: f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
    PriceType.GAS: f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AddonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the price sensors."""
    async_add_entities(
        PriceSensor(entry, coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class PriceSensor(AddonEntity, CoordinatorEntity[PriceCoordinator], SensorEntity):
    """Current price including the provider offset, with today/tomorrow attributes."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 5
    # The price lists are large; keep them out of the recorder database
    _unrecorded_attributes = frozenset({ATTR_PRICES_TODAY, ATTR_PRICES_TOMORROW})

    def __init__(self, entry: AddonConfigEntry, coordinator: PriceCoordinator) -> None:
        """Initialize the sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        AddonEntity.__init__(self, entry, f"{coordinator.price_type}_price")
        self._attr_native_unit_of_measurement = UNITS[coordinator.price_type]

    def _with_offset(self, points: list[PricePoint]) -> list[dict[str, Any]]:
        offset = self.coordinator.offset
        return [
            {"time": point.start.isoformat(), "price": round(point.price + offset, 6)}
            for point in points
        ]

    @property
    def available(self) -> bool:
        """Return True when today's prices are known."""
        return bool(self.coordinator.today)

    @property
    def native_value(self) -> float | None:
        """Return the price of the current interval."""
        if (point := current_point(self.coordinator.today, dt_util.now())) is None:
            return None
        return round(point.price + self.coordinator.offset, 6)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the price lists, in the same format as the old template sensor."""
        return {
            ATTR_PRICES_TODAY: self._with_offset(self.coordinator.today),
            ATTR_PRICES_TOMORROW: self._with_offset(self.coordinator.tomorrow),
        }
