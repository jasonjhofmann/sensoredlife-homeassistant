"""Tests for the SensoredLife async API client."""

from __future__ import annotations

import time

import pytest
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.sensoredlife.api import (
    SensoredLifeAuthError,
    SensoredLifeClient,
    SensoredLifeConnectionError,
)
from custom_components.sensoredlife.const import BASE_URL, DEVICES_PATH, LOGIN_PATH

ROOT_URL = f"{BASE_URL}/"
LOGIN_URL = f"{BASE_URL}{LOGIN_PATH}"


def _devices_url(user_id: str | int) -> str:
    return f"{BASE_URL}{DEVICES_PATH.format(user_id=user_id)}"


def _token_body(expires_offset: int = 30 * 86400) -> dict:
    return {
        "Id": 99999,
        "AccessToken": "tok-abc",
        "TokenExpiration": int(time.time()) + expires_offset,
    }


async def test_login_and_fetch(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    devices_payload,
) -> None:
    """A normal flow logs in once and returns parsed gateways."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json=_token_body())
    aioclient_mock.get(_devices_url(99999), json=devices_payload)

    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    gateways = await client.async_get_gateways()

    assert "350000000000001" in gateways
    # Login happened exactly once; token reused on a second fetch.
    await client.async_get_gateways()
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]) == LOGIN_URL) == 1


async def test_login_sends_xsrf_header(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    devices_payload,
) -> None:
    """The XSRF-TOKEN cookie from GET / is echoed (URL-decoded) on login."""
    aioclient_mock.get(ROOT_URL, cookies={"XSRF-TOKEN": "abc%20def"})
    aioclient_mock.post(LOGIN_URL, json=_token_body())
    aioclient_mock.get(_devices_url(99999), json=devices_payload)

    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    await client.async_get_gateways()

    login_calls = [c for c in aioclient_mock.mock_calls if str(c[1]) == LOGIN_URL]
    assert login_calls
    assert login_calls[0][3]["X-XSRF-TOKEN"] == "abc def"


async def test_login_client_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A transport error on login maps to a connection error."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, exc=ClientError())
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeConnectionError):
        await client.async_login()


async def test_devices_client_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A transport error fetching devices maps to a connection error."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json=_token_body())
    aioclient_mock.get(_devices_url(99999), exc=ClientError())
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeConnectionError):
        await client.async_get_gateways()


async def test_login_invalid_credentials(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 login with no token is treated as bad credentials."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json={"Id": None, "AccessToken": None})
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeAuthError):
        await client.async_login()


async def test_login_http_401(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 on login raises an auth error."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, status=401)
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeAuthError):
        await client.async_login()


async def test_login_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 500 on login raises a connection error."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, status=500)
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeConnectionError):
        await client.async_login()


async def test_token_rejected_relogin_still_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A persistent 401 on the devices call re-logs in once, then gives up."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json=_token_body())
    aioclient_mock.get(_devices_url(99999), status=401)
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    # First 401 -> re-login -> second 401 propagates as an auth error.
    with pytest.raises(SensoredLifeAuthError):
        await client.async_get_gateways()
    # Re-login happened: two POSTs total (initial + retry).
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]) == LOGIN_URL) == 2


async def test_devices_bad_shape(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-list devices payload raises a connection error."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json=_token_body())
    aioclient_mock.get(_devices_url(99999), json={"unexpected": "object"})
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")
    with pytest.raises(SensoredLifeConnectionError):
        await client.async_get_gateways()


async def test_expired_token_refreshes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    devices_payload,
) -> None:
    """A token within the refresh buffer triggers a fresh login."""
    aioclient_mock.get(ROOT_URL)
    aioclient_mock.post(LOGIN_URL, json=_token_body(expires_offset=10))
    aioclient_mock.get(_devices_url(99999), json=devices_payload)
    client = SensoredLifeClient(async_create_clientsession(hass), "u", "p")

    await client.async_get_gateways()
    await client.async_get_gateways()
    # Token always near-expiry -> login on each call.
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]) == LOGIN_URL) == 2
