from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DvsaMotClient, MotApiError, MotAuthError, MotNotFoundError
from .const import DOMAIN


class DvsaMotCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: DvsaMotClient,
        registrations: list[str],
        update_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self.registrations = [r.strip().replace(" ", "").upper() for r in registrations if r.strip()]

    async def _async_update_data(self) -> dict[str, Any]:
        results: dict[str, Any] = {}

        async def fetch(reg: str) -> None:
            try:
                results[reg] = await self.client.vehicle_by_registration(reg)
            except MotNotFoundError:
                results[reg] = {"_error": "not_found"}
            except MotAuthError as e:
                raise UpdateFailed(f"Auth error: {e}") from e
            except MotApiError as e:
                results[reg] = {"_error": "api_error", "message": str(e)}

        sem = asyncio.Semaphore(2)

        async def guarded(reg: str) -> None:
            async with sem:
                await fetch(reg)

        await asyncio.gather(*(guarded(r) for r in self.registrations))
        return results
