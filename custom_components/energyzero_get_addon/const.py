"""Constants for the Energy Zero Get Addon integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "energyzero_get_addon"
ENERGYZERO_DOMAIN: Final = "energyzero"
NAME: Final = "Energy Zero Get Addon"

CONF_ENERGYZERO_ENTRY: Final = "energyzero_entry_id"

# General options
CONF_INCL_VAT: Final = "incl_vat"
CONF_REFRESH_MINUTE: Final = "refresh_minute"
CONF_STARTUP_DELAY: Final = "startup_delay"

# Electricity only options
CONF_INTERVAL: Final = "interval"
CONF_PRICE_TYPE: Final = "price_type"
INTERVALS: Final = ("hour", "quarter")
PRICE_TYPES: Final = ("market", "all_in")
DEFAULT_INTERVAL: Final = "hour"
DEFAULT_PRICE_TYPE: Final = "market"

# Per price type options (stored as "<price_type>_<option>")
CONF_OFFSET: Final = "offset"
CONF_TODAY_ATTEMPTS: Final = "today_attempts"
CONF_TOMORROW_ATTEMPTS: Final = "tomorrow_attempts"
CONF_RETRY_DELAY: Final = "retry_delay"
CONF_TOMORROW_AFTER: Final = "tomorrow_after"
# Minimum hours of a day covered by prices (key kept for compatibility)
CONF_MIN_ENTRIES: Final = "min_entries"

PER_TYPE_OPTIONS: Final = (
    CONF_OFFSET,
    CONF_TODAY_ATTEMPTS,
    CONF_TOMORROW_ATTEMPTS,
    CONF_RETRY_DELAY,
    CONF_TOMORROW_AFTER,
    CONF_MIN_ENTRIES,
)

DEFAULT_INCL_VAT: Final = True
DEFAULT_REFRESH_MINUTE: Final = 7
DEFAULT_STARTUP_DELAY: Final = 45
DEFAULT_OFFSET: Final = 0.0
DEFAULT_TODAY_ATTEMPTS: Final = 5
DEFAULT_TOMORROW_ATTEMPTS: Final = 4
DEFAULT_RETRY_DELAY: Final = 20
DEFAULT_TOMORROW_AFTER: Final = "14:00:00"
DEFAULT_MIN_ENTRIES: Final = 13

ATTR_PRICES_TODAY: Final = "prices_today"
ATTR_PRICES_TOMORROW: Final = "prices_tomorrow"
ATTR_PRICE_TYPE: Final = "price_type"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

SERVICE_REFRESH: Final = "refresh"

STORAGE_VERSION: Final = 1


class PriceType(StrEnum):
    """Supported price types."""

    ELECTRICITY = "electricity"
    GAS = "gas"


# EnergyZero service used to fetch each price type
ENERGYZERO_SERVICES: Final = {
    PriceType.ELECTRICITY: "get_energy_prices",
    PriceType.GAS: "get_gas_prices",
}


def option_key(price_type: PriceType, option: str) -> str:
    """Return the flat options key for a per price type option."""
    return f"{price_type}_{option}"
