# Energy Zero Get Addon

<img src="custom_components/energyzero_get_addon/brand/icon.png" width="96" align="right" alt="icon">

A Home Assistant custom integration (installable via HACS) that turns the
[EnergyZero](https://www.home-assistant.io/integrations/energyzero/) day-ahead
prices into **electricity** and **gas** price sensors that include your energy
provider's offset (e.g. Eneco's purchase fee, energy tax and VAT surcharge).

It replaces the template-based `sensor.eneco_prices` trigger sensor, with the
same attribute format, and adds the same for gas.

## Requirements

- Home Assistant 2025.2 or newer
- The built-in **EnergyZero** integration, set up and working

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add this repository's URL, type *Integration*.
2. Install **Energy Zero Get Addon** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Energy Zero Get Addon*.
4. Pick your EnergyZero entry and enter the electricity (€/kWh) and gas (€/m³) offsets.

Manual install: copy `custom_components/energyzero_get_addon` into your
`config/custom_components` folder and restart.

## Entities

| Entity | Description |
| --- | --- |
| `sensor.energy_zero_get_addon_electricity_price` | Current electricity price + offset (€/kWh). Attributes `prices_today` / `prices_tomorrow` |
| `sensor.energy_zero_get_addon_gas_price` | Current gas price + offset (€/m³). Attributes `prices_today` / `prices_tomorrow` |
| `number.energy_zero_get_addon_electricity_offset` | Electricity provider offset, can be changed at any time |
| `number.energy_zero_get_addon_gas_offset` | Gas provider offset, can be changed at any time |
| `button.energy_zero_get_addon_refresh_prices` | Force a refresh of all prices |

The attributes use the same format as the old template sensor:

```yaml
prices_today:
  - time: "2026-11-01T00:00:00+01:00"
    price: 0.31234
  ...
```

`prices_tomorrow` stays empty until tomorrow's prices are complete. Sensors are
unavailable while no complete set of today's prices is known.

## Settings

All settings can be changed afterwards via *Configure* on the integration.
Electricity and gas each have their own section.

| Setting | Default | Notes |
| --- | --- | --- |
| Prices including VAT | on | Passed to EnergyZero as `incl_vat` |
| Refresh minute | 7 | Missing prices are fetched every hour at this minute |
| Startup delay | 45 s | Wait after Home Assistant starts before the first fetch |
| Provider offset | 0 | Added to every price (also available as number entity) |
| Price type *(electricity)* | market | `market` or EnergyZero's `all_in` price |
| Price interval *(electricity)* | hour | `hour` or `quarter` (15-minute prices) |
| Attempts for today's prices | 5 | |
| Attempts for tomorrow's prices | 4 | |
| Delay between attempts | 20 s | |
| Fetch tomorrow's prices from | 14:00 | |
| Minimum number of prices per day | 13 | Fewer prices = incomplete day (the old template used `> 12`) |

## Behaviour

- Prices are cached on disk, so the sensors keep working after a restart even
  when the EnergyZero API is temporarily down.
- Complete days are not fetched again; the hourly run only fetches what is
  missing. Use the button or the service to force a refresh.
- After midnight, tomorrow's prices become today's automatically.
- The current price is re-evaluated every quarter hour (the old template only
  updated at the hourly trigger).
- `prices_today` / `prices_tomorrow` are excluded from the recorder database to
  keep it small.

## Service `energyzero_get_addon.refresh`

Forces a refresh. Optional fields: `config_entry_id`, `price_type`
(`electricity` / `gas`).

```yaml
action: energyzero_get_addon.refresh
data:
  price_type: electricity
```

## Migrating from the template sensor

| Old | New |
| --- | --- |
| `sensor.eneco_prices` | `sensor.energy_zero_get_addon_electricity_price` (rename the entity ID to `sensor.eneco_prices` to keep dashboards/automations working, after removing the template sensor) |
| `input_number.eneco_base_price` | `number.energy_zero_get_addon_electricity_offset` |
| `input_button.refresh_eneco_prices` | `button.energy_zero_get_addon_refresh_prices` |
| event `eneco_prices_refresh` | action `energyzero_get_addon.refresh` |

## Development

```bash
pip install -r requirements_test.txt
pytest
```
