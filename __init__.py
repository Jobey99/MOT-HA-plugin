from __future__ import annotations

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import DvsaMotClient
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TOKEN_URL,
    CONF_SCOPE,
    CONF_REGISTRATIONS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
)
from .coordinator import DvsaMotCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = entry.data
    opts = entry.options

    api_key = data[CONF_API_KEY]
    client_id = data[CONF_CLIENT_ID]
    client_secret = data[CONF_CLIENT_SECRET]
    token_url = data[CONF_TOKEN_URL]
    scope = data[CONF_SCOPE]
    registrations = data[CONF_REGISTRATIONS]

    scan_interval = int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    base_url = opts.get("base_url", DEFAULT_BASE_URL)

    session: aiohttp.ClientSession = async_get_clientsession(hass)

    client = DvsaMotClient(
        session=session,
        api_key=api_key,
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        scope=scope,
        base_url=base_url,
    )

    coordinator = DvsaMotCoordinator(
        hass=hass,
        client=client,
        registrations=registrations,
        update_interval_seconds=scan_interval,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed:
        # Set up entities anyway; coordinator will retry on schedule
        pass

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
