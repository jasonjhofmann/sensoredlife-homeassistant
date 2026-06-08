"""Tests for SensoredLife setup, unload, and entity creation."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensoredlife.api import (
    SensoredLifeAuthError,
    SensoredLifeConnectionError,
)
from custom_components.sensoredlife.const import DOMAIN


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """The entry sets up, creates entities, and unloads cleanly."""
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    # Humidity is unit-agnostic, so its value passes through unconverted.
    humidity = hass.states.get("sensor.wine_cellar_humidity")
    assert humidity is not None
    assert float(humidity.state) == 31.9

    # Temperature is reported in native °F; HA may convert it for display, so we
    # assert on the (non-converted) safe-range attributes instead of the value.
    temp = hass.states.get("sensor.wine_cellar_temperature")
    assert temp is not None
    assert temp.attributes["safe_minimum"] == 40
    assert temp.attributes["in_safe_range"] is True

    # Mains power binary sensor on.
    power = hass.states.get("binary_sensor.wine_cellar_power")
    assert power.state == "on"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_devices_registered(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Gateways register as devices and SPucks as child devices."""
    await _setup(hass, mock_config_entry)
    registry = dr.async_get(hass)

    gateway = registry.async_get_device(identifiers={(DOMAIN, "350000000000001")})
    assert gateway is not None
    assert gateway.model == "MarCELL PRO"

    spuck = registry.async_get_device(identifiers={(DOMAIN, "AAAA0002")})
    assert spuck is not None
    assert spuck.via_device_id == gateway.id


async def test_offline_spuck_unavailable(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """A SPuck returning the sentinel reports unavailable, not a bogus value."""
    await _setup(hass, mock_config_entry)
    # Chest Freezer reports 999.9 / 99.9 sentinels -> unavailable.
    assert hass.states.get("sensor.chest_freezer_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.chest_freezer_humidity").state == STATE_UNAVAILABLE
    # Its battery is still a real reading.
    assert hass.states.get("sensor.chest_freezer_battery").state == "18"
    # Beverage Fridge has real readings (humidity is unit-agnostic).
    assert hass.states.get("sensor.beverage_fridge_temperature").state != STATE_UNAVAILABLE
    assert hass.states.get("sensor.beverage_fridge_humidity").state == "51.0"


async def test_setup_auth_failure_triggers_reauth(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """An auth error during refresh puts the entry into the reauth state."""
    mock_client.async_get_gateways = AsyncMock(side_effect=SensoredLifeAuthError)
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_setup_connection_failure_retries(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """A connection error during first refresh schedules a retry."""
    mock_client.async_get_gateways = AsyncMock(side_effect=SensoredLifeConnectionError)
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
