"""Price coordinator for the Energy Zero Get Addon integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENERGYZERO_ENTRY,
    CONF_INCL_VAT,
    CONF_INTERVAL,
    CONF_MIN_ENTRIES,
    CONF_OFFSET,
    CONF_PRICE_TYPE,
    CONF_RETRY_DELAY,
    CONF_TODAY_ATTEMPTS,
    CONF_TOMORROW_AFTER,
    CONF_TOMORROW_ATTEMPTS,
    DEFAULT_INCL_VAT,
    DEFAULT_INTERVAL,
    DEFAULT_MIN_ENTRIES,
    DEFAULT_OFFSET,
    DEFAULT_PRICE_TYPE,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TODAY_ATTEMPTS,
    DEFAULT_TOMORROW_AFTER,
    DEFAULT_TOMORROW_ATTEMPTS,
    DOMAIN,
    ENERGYZERO_DOMAIN,
    ENERGYZERO_SERVICES,
    STORAGE_VERSION,
    PriceType,
    option_key,
)

_LOGGER = logging.getLogger(__name__)

FALLBACK_INTERVAL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A single price for an interval starting at ``start``."""

    start: datetime
    price: float


@dataclass(slots=True)
class PriceData:
    """Raw prices (without offset) for today and tomorrow."""

    today: list[PricePoint] = field(default_factory=list)
    tomorrow: list[PricePoint] = field(default_factory=list)
    last_fetch: datetime | None = None


def _points_to_json(points: list[PricePoint]) -> list[list[Any]]:
    return [[point.start.isoformat(), point.price] for point in points]


def _points_from_json(raw: Any) -> list[PricePoint]:
    points: list[PricePoint] = []
    if not isinstance(raw, list):
        return points
    for item in raw:
        try:
            start = dt_util.parse_datetime(str(item[0]))
            price = float(item[1])
        except (IndexError, TypeError, ValueError):
            continue
        if start is not None:
            points.append(PricePoint(dt_util.as_local(start), price))
    return sorted(points, key=lambda point: point.start)


def current_point(points: list[PricePoint], now: datetime) -> PricePoint | None:
    """Return the price point whose interval contains ``now``."""
    for index, point in enumerate(points):
        if index + 1 < len(points):
            end = points[index + 1].start
        elif index > 0:
            end = point.start + (point.start - points[index - 1].start)
        else:
            end = point.start + FALLBACK_INTERVAL
        if point.start <= now < end:
            return point
    return None


class PriceCoordinator(DataUpdateCoordinator[PriceData]):
    """Fetch and cache prices of one price type via the EnergyZero integration."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, price_type: PriceType
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {price_type}",
            update_interval=None,
        )
        self.price_type = price_type
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.{price_type}"
        )
        self._lock = asyncio.Lock()
        self.data = PriceData()

    # Settings -------------------------------------------------------------

    def _option(self, option: str, default: Any) -> Any:
        return self.config_entry.options.get(
            option_key(self.price_type, option), default
        )

    @property
    def offset(self) -> float:
        """Return the provider offset added to every price."""
        return float(self._option(CONF_OFFSET, DEFAULT_OFFSET))

    @property
    def min_entries(self) -> int:
        """Return the number of entries required for a day to count as valid."""
        return int(self._option(CONF_MIN_ENTRIES, DEFAULT_MIN_ENTRIES))

    @property
    def _tomorrow_after(self) -> time:
        value = self._option(CONF_TOMORROW_AFTER, DEFAULT_TOMORROW_AFTER)
        return dt_util.parse_time(str(value)) or time(14, 0)

    # Validity -------------------------------------------------------------

    def is_valid_day(self, points: list[PricePoint], day: date) -> bool:
        """Return True when ``points`` hold enough prices for ``day``."""
        return len(points) >= self.min_entries and points[0].start.date() == day

    @property
    def today(self) -> list[PricePoint]:
        """Return today's prices, or an empty list when not (yet) available."""
        today = dt_util.now().date()
        return self.data.today if self.is_valid_day(self.data.today, today) else []

    @property
    def tomorrow(self) -> list[PricePoint]:
        """Return tomorrow's prices, or an empty list when not (yet) available."""
        today_points = self.today
        tomorrow = dt_util.now().date() + timedelta(days=1)
        points = self.data.tomorrow
        if (
            today_points
            and self.is_valid_day(points, tomorrow)
            and today_points[-1].start < points[0].start
        ):
            return points
        return []

    # Cache ----------------------------------------------------------------

    async def async_load_cache(self) -> None:
        """Restore previously fetched prices from storage."""
        if (stored := await self._store.async_load()) is None:
            return
        last_fetch = dt_util.parse_datetime(str(stored.get("last_fetch") or ""))
        self.data = PriceData(
            today=_points_from_json(stored.get("today")),
            tomorrow=_points_from_json(stored.get("tomorrow")),
            last_fetch=last_fetch,
        )
        self._roll_over()

    def _save_cache(self) -> None:
        data = self.data
        self.config_entry.async_create_task(
            self.hass,
            self._store.async_save(
                {
                    "today": _points_to_json(data.today),
                    "tomorrow": _points_to_json(data.tomorrow),
                    "last_fetch": (
                        data.last_fetch.isoformat() if data.last_fetch else None
                    ),
                }
            ),
            f"{DOMAIN} save {self.price_type} prices",
        )

    def _roll_over(self) -> bool:
        """Promote tomorrow's prices after midnight. Returns True on change."""
        today = dt_util.now().date()
        data = self.data
        if data.today and data.today[0].start.date() == today:
            return False
        if self.is_valid_day(data.tomorrow, today):
            self.data = PriceData(data.tomorrow, [], data.last_fetch)
            self._save_cache()
            return True
        return False

    async def async_remove_cache(self) -> None:
        """Remove the cache file."""
        await self._store.async_remove()

    # Updates --------------------------------------------------------------

    def async_tick(self) -> None:
        """Re-evaluate the current price (called on interval boundaries)."""
        self._roll_over()
        self.async_update_listeners()

    async def async_fetch(self, force: bool = False) -> None:
        """Fetch missing (or, when forced, all) prices and notify listeners."""
        async with self._lock:
            self.async_set_updated_data(await self._async_fetch(force))

    async def _async_update_data(self) -> PriceData:
        async with self._lock:
            return await self._async_fetch(force=False)

    async def _async_fetch(self, force: bool) -> PriceData:
        self._roll_over()
        now = dt_util.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        data = self.data
        new_today, new_tomorrow = data.today, data.tomorrow
        fetched = False

        if force or not self.is_valid_day(data.today, today):
            attempts = int(self._option(CONF_TODAY_ATTEMPTS, DEFAULT_TODAY_ATTEMPTS))
            if (points := await self._async_fetch_day(today, attempts)) is not None:
                new_today, fetched = points, True

        if now.time() >= self._tomorrow_after and (
            force or not self.is_valid_day(data.tomorrow, tomorrow)
        ):
            attempts = int(
                self._option(CONF_TOMORROW_ATTEMPTS, DEFAULT_TOMORROW_ATTEMPTS)
            )
            if (points := await self._async_fetch_day(tomorrow, attempts)) is not None:
                new_tomorrow, fetched = points, True

        if not fetched:
            return data

        self.data = PriceData(new_today, new_tomorrow, dt_util.utcnow())
        self._save_cache()
        return self.data

    async def _async_fetch_day(
        self, day: date, attempts: int
    ) -> list[PricePoint] | None:
        """Fetch prices for ``day``, retrying until enough entries are returned."""
        retry_delay = int(self._option(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY))
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                await asyncio.sleep(retry_delay)
            try:
                points = await self._async_call_energyzero(day)
            except Exception as err:  # noqa: BLE001 - equivalent of continue_on_error
                _LOGGER.debug(
                    "Fetching %s prices for %s failed (attempt %s/%s): %s",
                    self.price_type,
                    day,
                    attempt,
                    attempts,
                    err,
                )
                continue
            if len(points) >= self.min_entries:
                return points
            _LOGGER.debug(
                "Got %s %s prices for %s, need %s (attempt %s/%s)",
                len(points),
                self.price_type,
                day,
                self.min_entries,
                attempt,
                attempts,
            )
        _LOGGER.info(
            "No complete %s prices available for %s after %s attempts",
            self.price_type,
            day,
            attempts,
        )
        return None

    async def _async_call_energyzero(self, day: date) -> list[PricePoint]:
        energyzero_entry_id = self.config_entry.data[CONF_ENERGYZERO_ENTRY]
        energyzero_entry = self.hass.config_entries.async_get_entry(
            energyzero_entry_id
        )
        if (
            energyzero_entry is None
            or energyzero_entry.domain != ENERGYZERO_DOMAIN
            or energyzero_entry.state is not ConfigEntryState.LOADED
        ):
            raise RuntimeError("EnergyZero config entry is not loaded")

        service_data: dict[str, Any] = {
            "config_entry": energyzero_entry_id,
            "incl_vat": self.config_entry.options.get(CONF_INCL_VAT, DEFAULT_INCL_VAT),
            "start": day.isoformat(),
            "end": day.isoformat(),
        }
        if self.price_type is PriceType.ELECTRICITY:
            service_data[CONF_INTERVAL] = self._option(CONF_INTERVAL, DEFAULT_INTERVAL)
            service_data[CONF_PRICE_TYPE] = self._option(
                CONF_PRICE_TYPE, DEFAULT_PRICE_TYPE
            )
        response = await self.hass.services.async_call(
            ENERGYZERO_DOMAIN,
            ENERGYZERO_SERVICES[self.price_type],
            service_data,
            blocking=True,
            return_response=True,
        )

        points: dict[datetime, PricePoint] = {}
        for entry in (response or {}).get("prices") or []:
            try:
                start = dt_util.parse_datetime(str(entry["timestamp"]))
                price = float(entry["price"])
            except (KeyError, TypeError, ValueError):
                continue
            if start is None:
                continue
            start = dt_util.as_local(start)
            if start.date() == day:
                points[start] = PricePoint(start, price)
        return sorted(points.values(), key=lambda point: point.start)
