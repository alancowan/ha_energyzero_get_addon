"""Refresh button for the Energy Zero Get Addon integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AddonConfigEntry
from .entity import AddonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AddonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    async_add_entities([RefreshButton(entry)])


class RefreshButton(AddonEntity, ButtonEntity):
    """Force a refresh of all prices (replaces input_button.refresh_eneco_prices)."""

    def __init__(self, entry: AddonConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(entry, "refresh")
        self._entry = entry

    async def async_press(self) -> None:
        """Refresh electricity and gas prices in the background."""
        self._entry.async_create_background_task(
            self.hass,
            self._entry.runtime_data.async_fetch(force=True),
            "energyzero_get_addon refresh",
        )
