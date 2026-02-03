from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DvsaMotClient, MotApiError, MotAuthError
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TOKEN_URL,
    CONF_SCOPE,
    CONF_REGISTRATIONS,
    CONF_SCAN_INTERVAL,
    CONF_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCOPE_FALLBACK,
    DEFAULT_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class DvsaMotDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.registrations = self._get_registrations()

        session = async_get_clientsession(hass)

        scope = (entry.data.get(CONF_SCOPE) or DEFAULT_SCOPE_FALLBACK).strip()
        base_url = (entry.options.get(CONF_BASE_URL) or entry.data.get(CONF_BASE_URL) or DEFAULT_BASE_URL).strip()

        self.client = DvsaMotClient(
            session=session,
            api_key=entry.data[CONF_API_KEY],
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=entry.data[CONF_CLIENT_SECRET],
            token_url=entry.data[CONF_TOKEN_URL],
            scope=scope,
            base_url=base_url,
        )

        scan_seconds = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_seconds),
        )

    def _get_registrations(self) -> list[str]:
        regs = self.entry.options.get(CONF_REGISTRATIONS) or self.entry.data.get(CONF_REGISTRATIONS) or []
        cleaned: list[str] = []
        for r in regs:
            rr = str(r).strip().replace(" ", "").upper()
            if rr:
                cleaned.append(rr)
        # De-dupe while preserving order
        seen = set()
        out: list[str] = []
        for r in cleaned:
            if r not in seen:
                seen.add(r)
                out.append(r)
        return out

    async def _async_update_data(self) -> dict[str, Any]:
        # refresh registrations each update (in case reload didn't happen for some reason)
        self.registrations = self._get_registrations()

        results: dict[str, Any] = {}

        for reg in self.registrations:
            try:
                results[reg] = await self.client.vehicle_by_registration(reg)
            except MotAuthError as e:
                # auth errors should be loud
                raise UpdateFailed(f"Authentication failed: {e}") from e
            except MotApiError:
                # keep entity but mark error on that reg
                results[reg] = {"_error": "api_error"}
            except Exception as e:
                results[reg] = {"_error": "api_error", "detail": str(e)}

        return results
