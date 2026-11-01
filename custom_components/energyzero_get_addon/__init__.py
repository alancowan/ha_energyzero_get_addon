"""Energy Zero Get Addon: EnergyZero prices with a provider offset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_PRICE_TYPE,
    CONF_OFFSET,
    CONF_REFRESH_MINUTE,
    CONF_STARTUP_DELAY,
    DEFAULT_REFRESH_MINUTE,
    DEFAULT_STARTUP_DELAY,
    DOMAIN,
    SERVICE_REFRESH,
    PriceType,
    option_key,
)
from .coordinator import PriceCoordinator

try:
    import probatio as vol
except ImportError:  # Home Assistant releases before probatio
    import voluptuous as vol

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_PRICE_TYPE): vol.In([price_type.value for price_type in PriceType]),
    }
)

# Re-evaluate the current price on every quarter of an hour
TICK_MINUTES = [0, 15, 30, 45]


@dataclass(slots=True)
class AddonRuntimeData:
    """Runtime data of a config entry."""

    coordinators: dict[PriceType, PriceCoordinator]
    reload_options: dict[str, Any]

    async def async_fetch(
        self,
        force: bool = False,
        price_type: PriceType | None = None,
    ) -> None:
        """Fetch prices for one or all price types."""
        for kind, coordinator in self.coordinators.items():
            if price_type in (None, kind):
                await coordinator.async_fetch(force)


type AddonConfigEntry = ConfigEntry[AddonRuntimeData]


def _reload_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the options that require a reload when changed (all but offsets)."""
    offsets = {option_key(price_type, CONF_OFFSET) for price_type in PriceType}
    return {key: value for key, value in entry.options.items() if key not in offsets}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services."""

    async def async_refresh(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        entries: list[AddonConfigEntry] = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
            and entry_id in (None, entry.entry_id)
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_loaded_entry"
            )
        price_type = (
            PriceType(call.data[ATTR_PRICE_TYPE])
            if ATTR_PRICE_TYPE in call.data
            else None
        )
        for entry in entries:
            await entry.runtime_data.async_fetch(force=True, price_type=price_type)

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, async_refresh, schema=REFRESH_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AddonConfigEntry) -> bool:
    """Set up Energy Zero Get Addon from a config entry."""
    coordinators = {
        price_type: PriceCoordinator(hass, entry, price_type)
        for price_type in PriceType
    }
    for coordinator in coordinators.values():
        await coordinator.async_load_cache()

    runtime_data = AddonRuntimeData(coordinators, _reload_options(entry))
    entry.runtime_data = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _schedule_fetch(*_: Any) -> None:
        entry.async_create_background_task(
            hass, runtime_data.async_fetch(), f"{DOMAIN} fetch prices"
        )

    @callback
    def _tick(_: datetime) -> None:
        for coordinator in coordinators.values():
            coordinator.async_tick()

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _schedule_fetch,
            minute=entry.options.get(CONF_REFRESH_MINUTE, DEFAULT_REFRESH_MINUTE),
            second=0,
        )
    )
    entry.async_on_unload(
        async_track_time_change(hass, _tick, minute=TICK_MINUTES, second=0)
    )

    if hass.state is CoreState.running:
        # Added or reloaded while Home Assistant is running: fetch right away
        _schedule_fetch()
    else:
        # Give the EnergyZero integration time to start, as the automation did

        @callback
        def _at_started(_: HomeAssistant) -> None:
            entry.async_on_unload(
                async_call_later(
                    hass,
                    entry.options.get(CONF_STARTUP_DELAY, DEFAULT_STARTUP_DELAY),
                    _schedule_fetch,
                )
            )

        entry.async_on_unload(async_at_started(hass, _at_started))

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: AddonConfigEntry) -> None:
    """Apply offset changes in place, reload for any other option change."""
    if _reload_options(entry) != entry.runtime_data.reload_options:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    for coordinator in entry.runtime_data.coordinators.values():
        coordinator.async_update_listeners()


async def async_unload_entry(hass: HomeAssistant, entry: AddonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove cached prices when the config entry is deleted."""
    for price_type in PriceType:
        await PriceCoordinator(hass, entry, price_type).async_remove_cache()
