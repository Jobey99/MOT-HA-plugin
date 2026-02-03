# DVSA MOT History (Home Assistant)

This is a Home Assistant custom integration that pulls vehicle MOT information from the DVSA MOT History API. It uses OAuth2 client credentials to obtain an access token and then queries the vehicle record by registration.

The integration creates sensors for each configured registration, including MOT due date, days remaining, and a simple status value you can use for automations.

## Requirements

- Home Assistant with HACS installed (recommended) or the ability to copy a custom integration into `custom_components`.
- DVSA MOT History API access:
  - API key
  - Client ID
  - Client Secret
  - Token URL
  - Scope (typically `https://tapi.dvsa.gov.uk/.default`)


 ## Getting an API key (DVSA MOT History API)

This integration uses the DVSA MOT History API. To use it, you need to register for access. See the [DVSA registration page](https://documentation.history.mot.api.gov.uk/mot-history-api/register).

When your registration is approved, DVSA will issue the credentials this integration needs:
- API key (used as the `X-API-Key` header)
- Client ID
- Client secret
- Scope URL (commonly `https://tapi.dvsa.gov.uk/.default`)
- Access token URL (Azure AD v2 token endpoint) :contentReference[oaicite:1]{index=1}

Note: if an API key is not used for 90 days it may be automatically revoked, and you may need to contact DVSA support to restore access.


## Installation (HACS custom repository)

1. In Home Assistant, open HACS.
2. Go to Integrations.
3. Open the HACS menu (three dots) and choose “Custom repositories”.
4. Add this repository URL and select Category = Integration.
5. Install the integration from HACS.
6. Restart Home Assistant.


## HACS install link

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=Jobey99&repository=MOT-HA-plugin&category=integration)

## Manual installation

1. Copy `custom_components/dvsa_mot` into your Home Assistant config directory at:
   `/config/custom_components/dvsa_mot`
2. Restart Home Assistant.

## Setup

1. In Home Assistant, go to Settings → Devices & services → Add integration.
2. Search for “DVSA MOT History”.
3. Enter your credentials:
   - API key (sent as `X-API-Key`)
   - Client ID
   - Client Secret
   - Token URL (Azure AD v2 token endpoint)
   - Scope
4. Enter one or more registrations (comma-separated).

## Entities

For each registration, the integration creates sensors such as:

- `<REG> MOT due date`
- `<REG> MOT days remaining`
- `<REG> MOT status` (valid / expires_soon / expired)
- `<REG> Last MOT result`
- `<REG> Last MOT test date`
- `<REG> Vehicle` (make/model)

Additional attributes are attached to some sensors where available (make, model, colour, fuel type, etc).

## Options

You can adjust options under the integration’s Options menu:

- `warn_days`: Days before the due date to mark the status as `expires_soon` (default: 30)
- `scan_interval`: Update interval in seconds (default: 21600 / 6 hours)

## Notes

- The DVSA API requires both a Bearer token and an API key header. If authentication fails, check that the Client ID/Secret, Token URL, Scope, and API key are correct and active.
- Registrations are normalised by removing spaces and converting to uppercase.

## Troubleshooting

- Check Home Assistant logs for `dvsa_mot` to see authentication or API errors.
- If entities appear as unavailable, confirm the credentials can retrieve a token and that the API key is valid for the endpoint being called.
