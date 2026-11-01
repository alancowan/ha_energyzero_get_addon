"""Base entity for the Energy Zero Get Addon integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the device all entities of a config entry belong to."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        manufacturer="EnergyZero",
        model="Day-ahead prices",
        entry_type=DeviceEntryType.SERVICE,
    )


class AddonEntity(Entity):
    """Common attributes of all entities."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str) -> None:
        """Initialize the entity."""
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(entry)
