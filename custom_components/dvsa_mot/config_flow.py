from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DvsaMotClient, MotApiError, MotAuthError
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TOKEN_URL,
    CONF_SCOPE,
    CONF_REGISTRATIONS,
    CONF_WARN_DAYS,
    CONF_SCAN_INTERVAL,
    CONF_BASE_URL,
    DEFAULT_WARN_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCOPE_FALLBACK,
    DEFAULT_BASE_URL,
)


def _parse_regs(text: str) -> list[str]:
    regs: list[str] = []
    for part in (text or "").replace(";", ",").split(","):
        r = part.strip().replace(" ", "").upper()
        if r:
            regs.append(r)
    return regs


async def _validate(hass: HomeAssistant, data: dict) -> None:
    session = async_get_clientsession(hass)
    client = DvsaMotClient(
        session=session,
        api_key=data[CONF_API_KEY],
        client_id=data[CONF_CLIENT_ID],
        client_secret=data[CONF_CLIENT_SECRET],
        token_url=data[CONF_TOKEN_URL],
        scope=data[CONF_SCOPE],
        base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )

    regs: list[str] = data.get(CONF_REGISTRATIONS, [])
    # Validate by calling the API for the first reg
    if regs:
        await client.vehicle_by_registration(regs[0])
    else:
        # If no reg provided, we can't validate the vehicle endpoint
        # (still allows creating an entry; user can add regs in Options)
        return


class DvsaMotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            regs = _parse_regs(user_input.get(CONF_REGISTRATIONS, ""))

            data = {
                CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                CONF_TOKEN_URL: user_input[CONF_TOKEN_URL].strip(),
                CONF_SCOPE: (user_input.get(CONF_SCOPE) or DEFAULT_SCOPE_FALLBACK).strip(),
                CONF_BASE_URL: (user_input.get(CONF_BASE_URL) or DEFAULT_BASE_URL).strip(),
                # Store initial regs in data so first setup works immediately
                CONF_REGISTRATIONS: regs,
            }

            try:
                await _validate(self.hass, data)
            except MotAuthError:
                errors["base"] = "auth"
            except MotApiError:
                errors["base"] = "cannot_connect"
            else:
                # One entry per client_id (so you don't duplicate creds)
                await self.async_set_unique_id(data[CONF_CLIENT_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="DVSA MOT History", data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_TOKEN_URL): str,
                vol.Optional(CONF_SCOPE, default=DEFAULT_SCOPE_FALLBACK): str,
                vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                # Optional so you can create the entry and add cars later in Options
                vol.Optional(CONF_REGISTRATIONS, default=""): str,  # comma-separated
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return DvsaMotOptionsFlow(config_entry)


class DvsaMotOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            regs = _parse_regs(user_input.get(CONF_REGISTRATIONS, ""))
            base_url = (user_input.get(CONF_BASE_URL) or DEFAULT_BASE_URL).strip()

            return self.async_create_entry(
                title="",
                data={
                    CONF_REGISTRATIONS: regs,
                    CONF_WARN_DAYS: int(user_input.get(CONF_WARN_DAYS, DEFAULT_WARN_DAYS)),
                    CONF_SCAN_INTERVAL: int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                    CONF_BASE_URL: base_url,
                },
            )

        # Defaults: prefer options, fall back to original data
        current_regs = self.entry.options.get(CONF_REGISTRATIONS) or self.entry.data.get(CONF_REGISTRATIONS) or []
        regs_default = ", ".join(current_regs)

        schema = vol.Schema(
            {
                vol.Required(CONF_REGISTRATIONS, default=regs_default): str,
                vol.Optional(
                    CONF_WARN_DAYS,
                    default=self.entry.options.get(CONF_WARN_DAYS, DEFAULT_WARN_DAYS),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_BASE_URL,
                    default=self.entry.options.get(CONF_BASE_URL, self.entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL)),
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
