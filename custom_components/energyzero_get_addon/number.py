"""Provider offset numbers for the Energy Zero Get Addon integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AddonConfigEntry
from .const import CONF_OFFSET, option_key
from .coordinator import PriceCoordinator
from .entity import AddonEntity
from .sensor import UNITS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AddonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the offset numbers."""
    async_add_entities(
        OffsetNumber(entry, coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class OffsetNumber(AddonEntity, CoordinatorEntity[PriceCoordinator], NumberEntity):
    """Provider offset added to every price; stored in the config entry options."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.00001

    def __init__(self, entry: AddonConfigEntry, coordinator: PriceCoordinator) -> None:
        """Initialize the number."""
        CoordinatorEntity.__init__(self, coordinator)
        AddonEntity.__init__(self, entry, f"{coordinator.price_type}_offset")
        self._entry = entry
        self._attr_native_unit_of_measurement = UNITS[coordinator.price_type]

    @property
    def available(self) -> bool:
        """The offset can always be changed."""
        return True

    @property
    def native_value(self) -> float:
        """Return the current offset."""
        return self.coordinator.offset

    async def async_set_native_value(self, value: float) -> None:
        """Store the new offset; the update listener refreshes the sensors."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                **self._entry.options,
                option_key(self.coordinator.price_type, CONF_OFFSET): value,
            },
        )
