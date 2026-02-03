DOMAIN = "dvsa_mot"

CONF_API_KEY = "api_key"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TOKEN_URL = "token_url"
CONF_SCOPE = "scope"
CONF_REGISTRATIONS = "registrations"

CONF_WARN_DAYS = "warn_days"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_BASE_URL = "base_url"

DEFAULT_WARN_DAYS = 30
# seconds
DEFAULT_SCAN_INTERVAL = 6 * 60 * 60  # 6 hours

DEFAULT_SCOPE_FALLBACK = "https://tapi.dvsa.gov.uk/.default"
DEFAULT_BASE_URL = "https://history.mot.api.gov.uk"
