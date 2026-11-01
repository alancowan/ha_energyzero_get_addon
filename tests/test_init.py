"""Tests for the Energy Zero Get Addon integration."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from custom_components.energyzero_get_addon.const import DOMAIN

ELEC = "sensor.energy_zero_get_addon_electricity_price"
GAS = "sensor.energy_zero_get_addon_gas_price"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.freeze_time("2026-11-01 14:20:00+00:00")  # 15:20 Amsterdam
async def test_prices_today_and_tomorrow(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Prices are fetched, offset applied, and tomorrow is included after 14:00."""
    fake, _ = energyzero
    await _setup(hass, addon_entry)

    state = hass.states.get(ELEC)
    assert float(state.state) == pytest.approx(0.20 + 0.15 + 0.1)
    assert state.attributes["unit_of_measurement"] == "€/kWh"
    assert len(state.attributes["prices_today"]) == 24
    assert len(state.attributes["prices_tomorrow"]) == 24
    assert state.attributes["prices_today"][0] == {
        "time": "2026-11-01T00:00:00+01:00",
        "price": 0.3,
    }
    gas = hass.states.get(GAS)
    assert float(gas.state) == pytest.approx(1.11 + 0.5)
    assert gas.attributes["unit_of_measurement"] == "€/m³"
    # Gas days run 06:00-06:00, so each list holds the two overlapping gas days
    assert [p["time"] for p in gas.attributes["prices_today"]] == [
        "2026-10-31T06:00:00+01:00",
        "2026-11-01T06:00:00+01:00",
    ]
    assert [p["time"] for p in gas.attributes["prices_tomorrow"]] == [
        "2026-11-01T06:00:00+01:00",
        "2026-11-02T06:00:00+01:00",
    ]

    electricity_call = next(c for s, c in fake.calls if s == "get_energy_prices")
    assert electricity_call["incl_vat"] is True
    assert electricity_call["interval"] == "hour"
    assert electricity_call["price_type"] == "market"

    # Hourly trigger does not refetch complete data
    calls = len(fake.calls)
    async_fire_time_changed(hass, hass.config.time_zone and None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(fake.calls) == calls


@pytest.mark.freeze_time("2026-11-01 08:00:00+00:00")  # 09:00 Amsterdam
async def test_no_tomorrow_before_configured_time(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Tomorrow's prices are only requested after the configured time."""
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    assert len(fake.calls) == 2  # today electricity + today gas
    assert hass.states.get(ELEC).attributes["prices_tomorrow"] == []


@pytest.mark.freeze_time("2026-11-01 08:00:00+00:00")
async def test_retries_then_success(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Failed calls are retried up to the configured attempts."""
    fake, _ = energyzero
    fake.failures = 3
    await _setup(hass, addon_entry)
    # electricity: 3 failures + 1 success, gas: 1 success
    assert len(fake.calls) == 5
    assert hass.states.get(ELEC).state != "unavailable"


@pytest.mark.freeze_time("2026-11-01 08:00:00+00:00")
async def test_unavailable_without_data(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Sensor is unavailable when no complete day could be fetched."""
    fake, _ = energyzero
    fake.available_days = set()
    await _setup(hass, addon_entry)
    assert len(fake.calls) == 10  # 5 attempts each
    assert hass.states.get(ELEC).state == "unavailable"


@pytest.mark.freeze_time("2026-11-01 14:20:00+00:00")
async def test_offset_number_updates_sensor(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Changing the offset number updates the sensor without refetching."""
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    calls = len(fake.calls)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.energy_zero_get_addon_electricity_offset", "value": 0.25},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert float(hass.states.get(ELEC).state) == pytest.approx(0.35 + 0.25)
    assert hass.states.get(ELEC).attributes["prices_tomorrow"][0]["price"] == 0.45
    assert addon_entry.options["electricity_offset"] == 0.25
    assert len(fake.calls) == calls


async def test_midnight_rollover(
    hass: HomeAssistant,
    energyzero,
    addon_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Tomorrow's prices become today's after midnight without a new fetch."""
    freezer.move_to("2026-11-01 22:50:00+00:00")  # 23:50 Amsterdam
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    fake.available_days = set()  # API down after midnight

    freezer.move_to("2026-11-01 23:00:00+00:00")  # 00:00 Amsterdam
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(ELEC)
    assert float(state.state) == pytest.approx(0.20 + 0.1)
    assert state.attributes["prices_today"][0]["time"] == "2026-11-02T00:00:00+01:00"
    assert state.attributes["prices_tomorrow"] == []


@pytest.mark.freeze_time("2026-11-01 14:20:00+00:00")
async def test_refresh_service_and_button(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """The refresh service and button force a refetch."""
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    calls = len(fake.calls)
    await hass.services.async_call(
        DOMAIN, "refresh", {"price_type": "gas"}, blocking=True
    )
    assert len(fake.calls) == calls + 2  # gas today + tomorrow
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.energy_zero_get_addon_refresh_prices"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(fake.calls) == calls + 6


@pytest.mark.freeze_time("2026-11-01 14:20:00+00:00")
async def test_cache_restored_after_restart(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Cached prices are used after a reload when the API is unavailable."""
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    fake.available_days = set()
    assert await hass.config_entries.async_reload(addon_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ELEC)
    assert float(state.state) == pytest.approx(0.45)
    assert len(state.attributes["prices_tomorrow"]) == 24


async def test_config_flow(hass: HomeAssistant, energyzero) -> None:
    """The user step creates an entry with offsets."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"energyzero_entry_id": "ez_entry", "electricity_offset": 0.12, "gas_offset": 0.6},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["electricity_offset"] == 0.12
    assert result["options"]["gas_offset"] == 0.6
    assert result["options"]["electricity_today_attempts"] == 5


async def test_config_flow_requires_energyzero(hass: HomeAssistant) -> None:
    """The flow aborts when EnergyZero is not set up."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_energyzero"


@pytest.mark.freeze_time("2026-11-01 08:00:00+00:00")
async def test_options_flow(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Options are shown in sections and stored flat."""
    await _setup(hass, addon_entry)
    result = await hass.config_entries.options.async_init(addon_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "general": {"incl_vat": False, "refresh_minute": 9, "startup_delay": 30},
            "electricity": {
                "offset": 0.2,
                "price_type": "all_in",
                "interval": "quarter",
                "today_attempts": 3,
                "tomorrow_attempts": 2,
                "retry_delay": 10,
                "tomorrow_after": "13:30:00",
                "min_entries": 24,
            },
            "gas": {
                "offset": 0.7,
                "today_attempts": 3,
                "tomorrow_attempts": 2,
                "retry_delay": 10,
                "tomorrow_after": "15:00:00",
                "min_entries": 20,
            },
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    assert addon_entry.options["incl_vat"] is False
    assert addon_entry.options["refresh_minute"] == 9
    assert addon_entry.options["electricity_interval"] == "quarter"
    assert addon_entry.options["gas_min_entries"] == 20
    assert addon_entry.options["electricity_today_attempts"] == 3
    # The entry was reloaded with the new settings
    assert float(hass.states.get(GAS).state) == pytest.approx(1.11 + 0.7)


@pytest.mark.freeze_time("2026-11-01 03:30:00+00:00")  # 04:30 Amsterdam
async def test_gas_before_six_uses_previous_gas_day(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Before 06:00 the gas price of the previous gas day applies."""
    await _setup(hass, addon_entry)
    assert float(hass.states.get(GAS).state) == pytest.approx(1.41 + 0.5)


async def test_gas_midnight_rollover(
    hass: HomeAssistant,
    energyzero,
    addon_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Gas stays available across midnight and switches price at 06:00."""
    freezer.move_to("2026-11-01 22:50:00+00:00")  # 23:50 Amsterdam
    fake, _ = energyzero
    await _setup(hass, addon_entry)
    fake.available_days = set()

    freezer.move_to("2026-11-01 23:00:00+00:00")  # 00:00 Amsterdam
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(GAS).state) == pytest.approx(1.11 + 0.5)

    freezer.move_to("2026-11-02 05:00:00+00:00")  # 06:00 Amsterdam
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(GAS).state) == pytest.approx(1.12 + 0.5)


@pytest.mark.freeze_time("2026-11-01 14:20:00+00:00")
async def test_timestamp_only_response(
    hass: HomeAssistant, energyzero, addon_entry: MockConfigEntry
) -> None:
    """Responses without start/end (older EnergyZero versions) still work."""
    fake, _ = energyzero
    original = fake.prices

    def without_ranges(service, day):
        data = original(service, day)
        for entry in data["prices"]:
            del entry["start"], entry["end"]
        return data

    fake.prices = without_ranges
    await _setup(hass, addon_entry)
    assert float(hass.states.get(ELEC).state) == pytest.approx(0.45)
