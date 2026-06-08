"""Async client for the SensoredLife cloud API.

The login endpoint (``/LoginGateway.php``) is CSRF-protected with the Angular /
Laravel double-submit pattern: the server sets an ``XSRF-TOKEN`` cookie on a
page GET, and the client must echo that value in an ``X-XSRF-TOKEN`` header on
the POST (with ``Origin`` / ``Referer`` and an exact
``application/json;charset=UTF-8`` content type). So it GETs ``/`` to seed the
token, then logs in. The read-only ``/api/...`` calls only need the resulting
access token as a query parameter.

The caller supplies a *dedicated* aiohttp session (one with its own cookie jar,
e.g. ``async_create_clientsession``) so the XSRF cookie is isolated from Home
Assistant's shared session, and owns its lifecycle.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

import aiohttp
from aiohttp import ClientError, ClientResponseError

from .const import (
    BASE_URL,
    DEVICES_PATH,
    FORCE_UPDATE_PATH,
    LOGIN_PATH,
    TOKEN_REFRESH_BUFFER,
)
from .models import Gateway, parse_devices

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
_XSRF_COOKIE = "XSRF-TOKEN"


class SensoredLifeError(Exception):
    """Base error for the SensoredLife client."""


class SensoredLifeConnectionError(SensoredLifeError):
    """Raised when the cloud cannot be reached or returns an unexpected response."""


class SensoredLifeAuthError(SensoredLifeError):
    """Raised when credentials are rejected (bad login or token refused twice)."""


class SensoredLifeClient:
    """Log in for a token, then poll the devices feed over a cookie-jar session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        """Initialize the client with a cookie-jar session and credentials."""
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._user_id: int | str | None = None
        self._expires: int = 0
        # Last XSRF token (URL-decoded), needed to echo on state-changing POSTs.
        self._xsrf: str | None = None

    @property
    def _token_fresh(self) -> bool:
        if not self._token:
            return False
        now = int(datetime.now(UTC).timestamp())
        return (self._expires - now) > TOKEN_REFRESH_BUFFER.total_seconds()

    async def _seed_xsrf(self) -> str | None:
        """GET the site root so the server hands us an XSRF-TOKEN cookie."""
        async with self._session.get(
            f"{BASE_URL}/",
            headers={"User-Agent": _USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            morsel = resp.cookies.get(_XSRF_COOKIE)
            if morsel is not None:
                return morsel.value
        for cookie in self._session.cookie_jar:
            if cookie.key == _XSRF_COOKIE:
                return cookie.value
        return None

    def _post_headers(self) -> dict[str, str]:
        """Browser-shaped headers for a state-changing POST, with the XSRF echo."""
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        }
        if self._xsrf:
            headers["X-XSRF-TOKEN"] = self._xsrf
        return headers

    async def async_login(self) -> None:
        """Authenticate and cache the access token (raises on bad credentials)."""
        try:
            xsrf = await self._seed_xsrf()
            self._xsrf = unquote(xsrf) if xsrf else None
            async with self._session.post(
                f"{BASE_URL}{LOGIN_PATH}",
                data=json.dumps(
                    {"username": self._username, "password": self._password}
                ),
                headers=self._post_headers(),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise SensoredLifeAuthError("Invalid username or password")
                resp.raise_for_status()
                body = await resp.json(content_type=None)
        except ClientResponseError as err:
            raise SensoredLifeConnectionError(
                f"Login HTTP error: {err.status}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise SensoredLifeConnectionError(f"Login failed: {err}") from err

        token = body.get("AccessToken") if isinstance(body, dict) else None
        user_id = body.get("Id") if isinstance(body, dict) else None
        if not token or user_id is None:
            # A 200 with no token is how the login endpoint signals bad creds.
            raise SensoredLifeAuthError("Login response did not contain a token")
        self._token = token
        self._user_id = user_id
        self._expires = int(body.get("TokenExpiration") or 0)

    async def async_get_gateways(self) -> dict[str, Gateway]:
        """Return all gateways (with SPucks), refreshing the token as needed."""
        if not self._token_fresh:
            await self.async_login()

        try:
            payload = await self._get_devices()
        except SensoredLifeAuthError:
            # Token went stale early — try exactly one fresh login, then retry.
            _LOGGER.debug("Token rejected; re-authenticating once")
            await self.async_login()
            payload = await self._get_devices()

        if not isinstance(payload, list):
            raise SensoredLifeConnectionError("Unexpected devices response shape")
        return parse_devices(payload)

    async def async_force_update(self, imei: str) -> None:
        """Ask a gateway to call in now (spends one instant-update credit)."""
        if not self._token_fresh:
            await self.async_login()
        try:
            await self._send_force_update(imei)
        except SensoredLifeAuthError:
            _LOGGER.debug("Token rejected on force-update; re-authenticating once")
            await self.async_login()
            await self._send_force_update(imei)

    async def _send_force_update(self, imei: str) -> None:
        url = f"{BASE_URL}{FORCE_UPDATE_PATH.format(imei=imei)}"
        try:
            async with self._session.post(
                url,
                params={"access_token": self._token or ""},
                data=json.dumps({"params": {"access_token": self._token}}),
                headers=self._post_headers(),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise SensoredLifeAuthError("Access token rejected")
                resp.raise_for_status()
        except ClientResponseError as err:
            raise SensoredLifeConnectionError(
                f"Force-update HTTP error: {err.status}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise SensoredLifeConnectionError(f"Force-update failed: {err}") from err

    async def _get_devices(self) -> Any:
        path = DEVICES_PATH.format(user_id=self._user_id)
        try:
            async with self._session.get(
                f"{BASE_URL}{path}",
                params={"access_token": self._token or ""},
                headers={"User-Agent": _USER_AGENT, "Referer": f"{BASE_URL}/"},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise SensoredLifeAuthError("Access token rejected")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except ClientResponseError as err:
            raise SensoredLifeConnectionError(
                f"Devices HTTP error: {err.status}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise SensoredLifeConnectionError(f"Devices fetch failed: {err}") from err
