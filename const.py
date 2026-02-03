from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "dvsa_mot"
PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_API_KEY = "api_key"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TOKEN_URL = "token_url"
CONF_SCOPE = "scope"
CONF_REGISTRATIONS = "registrations"

CONF_WARN_DAYS = "warn_days"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_WARN_DAYS = 30
DEFAULT_SCAN_INTERVAL = 6 * 60 * 60  # seconds
DEFAULT_SCOPE_FALLBACK = "https://tapi.dvsa.gov.uk/.default"
DEFAULT_TOKEN_URL = "https://login.microsoftonline.com/a455b827-244f-4c97-b5b4-ce5d13b4d00c/oauth2/v2.0/token"
DEFAULT_BASE_URL = "https://history.mot.api.gov.uk"
