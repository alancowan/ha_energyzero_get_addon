"""Config flow for the Energy Zero Get Addon integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_ENERGYZERO_ENTRY,
    CONF_INCL_VAT,
    CONF_INTERVAL,
    CONF_MIN_ENTRIES,
    CONF_OFFSET,
    CONF_PRICE_TYPE,
    CONF_REFRESH_MINUTE,
    CONF_RETRY_DELAY,
    CONF_STARTUP_DELAY,
    CONF_TODAY_ATTEMPTS,
    CONF_TOMORROW_AFTER,
    CONF_TOMORROW_ATTEMPTS,
    DEFAULT_INCL_VAT,
    DEFAULT_INTERVAL,
    DEFAULT_MIN_ENTRIES,
    DEFAULT_OFFSET,
    DEFAULT_PRICE_TYPE,
    DEFAULT_REFRESH_MINUTE,
    DEFAULT_RETRY_DELAY,
    DEFAULT_STARTUP_DELAY,
    DEFAULT_TODAY_ATTEMPTS,
    DEFAULT_TOMORROW_AFTER,
    DEFAULT_TOMORROW_ATTEMPTS,
    DOMAIN,
    ENERGYZERO_DOMAIN,
    INTERVALS,
    NAME,
    PRICE_TYPES,
    PriceType,
    option_key,
)

try:
    import probatio as vol
except ImportError:  # Home Assistant releases before probatio
    import voluptuous as vol

SECTION_GENERAL = "general"

GENERAL_DEFAULTS: dict[str, Any] = {
    CONF_INCL_VAT: DEFAULT_INCL_VAT,
    CONF_REFRESH_MINUTE: DEFAULT_REFRESH_MINUTE,
    CONF_STARTUP_DELAY: DEFAULT_STARTUP_DELAY,
}

PER_TYPE_DEFAULTS: dict[str, Any] = {
    CONF_OFFSET: DEFAULT_OFFSET,
    CONF_TODAY_ATTEMPTS: DEFAULT_TODAY_ATTEMPTS,
    CONF_TOMORROW_ATTEMPTS: DEFAULT_TOMORROW_ATTEMPTS,
    CONF_RETRY_DELAY: DEFAULT_RETRY_DELAY,
    CONF_TOMORROW_AFTER: DEFAULT_TOMORROW_AFTER,
    CONF_MIN_ENTRIES: DEFAULT_MIN_ENTRIES,
}

ELECTRICITY_DEFAULTS: dict[str, Any] = {
    CONF_INTERVAL: DEFAULT_INTERVAL,
    CONF_PRICE_TYPE: DEFAULT_PRICE_TYPE,
}


def default_options() -> dict[str, Any]:
    """Return the flat default options."""
    options = dict(GENERAL_DEFAULTS)
    for price_type in PriceType:
        defaults = dict(PER_TYPE_DEFAULTS)
        if price_type is PriceType.ELECTRICITY:
            defaults |= ELECTRICITY_DEFAULTS
        options |= {option_key(price_type, key): value for key, value in defaults.items()}
    return options


def _offset_selector(unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-10,
            max=10,
            step="any",
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _int_selector(
    minimum: int, maximum: int, unit: str | None = None
) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


UNIT_LABELS = {PriceType.ELECTRICITY: "€/kWh", PriceType.GAS: "€/m³"}


def _price_type_schema(price_type: PriceType) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_OFFSET): _offset_selector(UNIT_LABELS[price_type]),
    }
    if price_type is PriceType.ELECTRICITY:
        fields |= {
            vol.Required(CONF_PRICE_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(PRICE_TYPES), translation_key=CONF_PRICE_TYPE
                )
            ),
            vol.Required(CONF_INTERVAL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(INTERVALS), translation_key=CONF_INTERVAL
                )
            ),
        }
    fields |= {
        vol.Required(CONF_TODAY_ATTEMPTS): _int_selector(1, 20),
        vol.Required(CONF_TOMORROW_ATTEMPTS): _int_selector(1, 20),
        vol.Required(CONF_RETRY_DELAY): _int_selector(1, 600, "s"),
        vol.Required(CONF_TOMORROW_AFTER): selector.TimeSelector(),
        vol.Required(CONF_MIN_ENTRIES): _int_selector(1, 100),
    }
    return vol.Schema(fields)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(SECTION_GENERAL): section(
            vol.Schema(
                {
                    vol.Required(CONF_INCL_VAT): selector.BooleanSelector(),
                    vol.Required(CONF_REFRESH_MINUTE): _int_selector(0, 59),
                    vol.Required(CONF_STARTUP_DELAY): _int_selector(0, 600, "s"),
                }
            )
        ),
        **{
            vol.Required(price_type.value): section(
                _price_type_schema(price_type), {"collapsed": True}
            )
            for price_type in PriceType
        },
    }
)


def _to_sections(options: dict[str, Any]) -> dict[str, Any]:
    """Convert flat options to the nested form shown in the options flow."""
    merged = default_options() | options
    nested: dict[str, Any] = {
        SECTION_GENERAL: {key: merged[key] for key in GENERAL_DEFAULTS}
    }
    for price_type in PriceType:
        prefix = f"{price_type}_"
        nested[price_type.value] = {
            key.removeprefix(prefix): value
            for key, value in merged.items()
            if key.startswith(prefix)
        }
    return nested


def _from_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Convert nested options flow input to flat options."""
    options: dict[str, Any] = dict(user_input.get(SECTION_GENERAL, {}))
    for price_type in PriceType:
        for key, value in user_input.get(price_type.value, {}).items():
            options[option_key(price_type, key)] = value
    # Number selectors return floats; store whole numbers as int
    for key in (CONF_REFRESH_MINUTE, CONF_STARTUP_DELAY):
        options[key] = int(options[key])
    for price_type in PriceType:
        for key in (
            CONF_TODAY_ATTEMPTS,
            CONF_TOMORROW_ATTEMPTS,
            CONF_RETRY_DELAY,
            CONF_MIN_ENTRIES,
        ):
            options[option_key(price_type, key)] = int(
                options[option_key(price_type, key)]
            )
        options[option_key(price_type, CONF_OFFSET)] = float(
            options[option_key(price_type, CONF_OFFSET)]
        )
    return options


class EnergyZeroGetAddonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the EnergyZero entry and the provider offsets."""
        energyzero_entries = self.hass.config_entries.async_entries(ENERGYZERO_DOMAIN)
        if not energyzero_entries:
            return self.async_abort(reason="no_energyzero")

        if user_input is not None:
            energyzero_entry_id = user_input[CONF_ENERGYZERO_ENTRY]
            await self.async_set_unique_id(energyzero_entry_id)
            self._abort_if_unique_id_configured()
            options = default_options()
            for price_type in PriceType:
                key = option_key(price_type, CONF_OFFSET)
                options[key] = float(user_input[key])
            return self.async_create_entry(
                title=NAME,
                data={CONF_ENERGYZERO_ENTRY: energyzero_entry_id},
                options=options,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENERGYZERO_ENTRY,
                        default=energyzero_entries[0].entry_id,
                    ): selector.ConfigEntrySelector(
                        selector.ConfigEntrySelectorConfig(
                            integration=ENERGYZERO_DOMAIN
                        )
                    ),
                    **{
                        vol.Required(
                            option_key(price_type, CONF_OFFSET), default=DEFAULT_OFFSET
                        ): _offset_selector(UNIT_LABELS[price_type])
                        for price_type in PriceType
                    },
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EnergyZeroGetAddonOptionsFlow()


class EnergyZeroGetAddonOptionsFlow(OptionsFlow):
    """Change offsets, schedule and retry settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=_from_sections(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, _to_sections(dict(self.config_entry.options))
            ),
        )
