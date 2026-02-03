from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp


class MotApiError(Exception):
    """Base error."""


class MotAuthError(MotApiError):
    """Authentication or authorization error."""


class MotNotFoundError(MotApiError):
    """Vehicle not found."""


@dataclass
class Token:
    access_token: str
    expires_at: datetime  # UTC


class DvsaMotClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str,
        base_url: str,
        request_timeout: int = 30,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._token: Optional[Token] = None
        self._token_lock = asyncio.Lock()

    async def _get_token(self) -> str:
        async with self._token_lock:
            now = datetime.now(timezone.utc)
            if self._token and self._token.expires_at - now > timedelta(seconds=60):
                return self._token.access_token

            data = {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._scope,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            try:
                async with self._session.post(
                    self._token_url,
                    data=data,
                    headers=headers,
                    timeout=self._timeout,
                ) as resp:
                    text = await resp.text()
                    if resp.status in (401, 403):
                        raise MotAuthError(f"Token request unauthorized ({resp.status}): {text[:200]}")
                    if resp.status >= 400:
                        raise MotApiError(f"Token request failed ({resp.status}): {text[:200]}")
                    payload = await resp.json()
            except aiohttp.ClientError as e:
                raise MotApiError(f"Token request error: {e}") from e

            access_token = payload.get("access_token")
            expires_in = payload.get("expires_in", 3600)
            if not access_token:
                raise MotApiError("Token response missing access_token")

            expires_at = now + timedelta(seconds=int(expires_in))
            self._token = Token(access_token=access_token, expires_at=expires_at)
            return access_token

    async def _request(self, method: str, path: str) -> Any:
        token = await self._get_token()

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-API-Key": self._api_key,
            "Accept": "application/json",
        }

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                timeout=self._timeout,
            ) as resp:
                if resp.status == 404:
                    raise MotNotFoundError("Vehicle not found")
                if resp.status in (401, 403):
                    body = await resp.text()
                    raise MotAuthError(f"Unauthorized ({resp.status}): {body[:200]}")
                if resp.status >= 400:
                    body = await resp.text()
                    raise MotApiError(f"API error ({resp.status}): {body[:200]}")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise MotApiError(f"Request error: {e}") from e

    async def vehicle_by_registration(self, registration: str) -> dict[str, Any]:
        reg = registration.strip().replace(" ", "").upper()
        return await self._request("GET", f"/v1/trade/vehicles/registration/{reg}")

    async def vehicle_by_vin(self, vin: str) -> dict[str, Any]:
        v = vin.strip().upper()
        return await self._request("GET", f"/v1/trade/vehicles/vin/{v}")
