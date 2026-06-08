"""Fixtures for SensoredLife tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensoredlife.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.sensoredlife.models import parse_devices

USERNAME = "jason@example.com"
PASSWORD = "hunter2"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


def _load_fixture() -> list:
    path = Path(__file__).parent / "fixtures" / "devices.json"
    return json.loads(path.read_text())


@pytest.fixture
def devices_payload() -> list:
    """The raw /devices JSON payload."""
    return _load_fixture()


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured SensoredLife config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=USERNAME,
        unique_id=USERNAME.lower(),
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
    )


@pytest.fixture
def mock_client(devices_payload):
    """Patch the API client so no network calls happen."""
    gateways = parse_devices(devices_payload)
    with (
        patch(
            "custom_components.sensoredlife.coordinator.SensoredLifeClient",
            autospec=True,
        ) as coord_client,
        patch(
            "custom_components.sensoredlife.config_flow.SensoredLifeClient",
            autospec=True,
        ) as flow_client,
    ):
        # Both call sites must resolve to the SAME mock instance so a test can
        # tweak login/fetch behavior once and have it apply everywhere.
        instance = coord_client.return_value
        flow_client.return_value = instance
        instance.async_login = AsyncMock(return_value=None)
        instance.async_get_gateways = AsyncMock(return_value=gateways)
        yield instance
