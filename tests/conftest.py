"""Fixtures for Energy Zero Get Addon tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.energyzero_get_addon.config_flow import default_options
from custom_components.energyzero_get_addon.const import (
    CONF_ENERGYZERO_ENTRY,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


class FakeEnergyZero:
    """Stand-in for the EnergyZero services."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.failures = 0
        self.available_days: set[date] | None = None  # None = every day

    def prices(self, service: str, day: date) -> dict[str, Any]:
        start = dt_util.start_of_local_day(day)
        if service == "get_gas_prices":
            # Gas days run 06:00-06:00: return the two that overlap ``day``
            return {
                "prices": [
                    self._entry(
                        start + timedelta(days=offset, hours=6),
                        timedelta(days=1),
                        round(1.10 + (day + timedelta(days=offset)).day / 100, 4),
                    )
                    for offset in (-1, 0)
                ]
            }
        return {
            "prices": [
                self._entry(
                    start + timedelta(hours=hour),
                    timedelta(hours=1),
                    round(0.20 + hour / 100, 4),
                )
                for hour in range(24)
            ]
        }

    @staticmethod
    def _entry(start, length: timedelta, price: float) -> dict[str, Any]:
        return {
            "price": price,
            "timestamp": str(dt_util.as_utc(start)),
            "start": str(dt_util.as_utc(start)),
            "end": str(dt_util.as_utc(start + length)),
        }

    def handler(self, service: str):
        async def _handle(call: ServiceCall) -> dict[str, Any]:
            self.calls.append((service, dict(call.data)))
            if self.failures:
                self.failures -= 1
                raise ServiceValidationError("no data")
            day = date.fromisoformat(call.data["start"])
            if self.available_days is not None and day not in self.available_days:
                return {"prices": []}
            return self.prices(service, day)

        return _handle


@pytest.fixture
async def energyzero(hass: HomeAssistant) -> tuple[FakeEnergyZero, MockConfigEntry]:
    """Register fake EnergyZero services and a loaded EnergyZero entry."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    hass.config.components.add("energyzero")
    fake = FakeEnergyZero()
    for service in ("get_energy_prices", "get_gas_prices"):
        hass.services.async_register(
            "energyzero",
            service,
            fake.handler(service),
            supports_response=SupportsResponse.ONLY,
        )
    ez_entry = MockConfigEntry(domain="energyzero", entry_id="ez_entry")
    ez_entry.add_to_hass(hass)
    ez_entry.mock_state(hass, ConfigEntryState.LOADED)
    return fake, ez_entry


@pytest.fixture
def addon_entry() -> MockConfigEntry:
    """Return an addon config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="ez_entry",
        data={CONF_ENERGYZERO_ENTRY: "ez_entry"},
        options=default_options()
        | {
            "electricity_offset": 0.1,
            "gas_offset": 0.5,
            "electricity_retry_delay": 0,
            "gas_retry_delay": 0,
        },
    )
