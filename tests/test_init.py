"""Tests for SensoredLife setup, unload, and entity creation."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.sensoredlife.api import (
    SensoredLifeAuthError,
    SensoredLifeConnectionError,
)
from custom_components.sensoredlife.const import DOMAIN, FORCE_UPDATE_SETTLE


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
    # Generic family name — the API exposes no model/tier indicator.
    assert gateway.model == "MarCELL"

    spuck = registry.async_get_device(identifiers={(DOMAIN, "AAAA0002")})
    assert spuck is not None
    assert spuck.via_device_id == gateway.id


async def test_offline_spuck_unavailable(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """A SPuck returning the sentinel reports unavailable, not a bogus value."""
    await _setup(hass, mock_config_entry)
    # Chest Freezer reports 999.9 / 99.9 sentinels -> unavailable.
    assert (
        hass.states.get("sensor.chest_freezer_temperature").state == STATE_UNAVAILABLE
    )
    assert hass.states.get("sensor.chest_freezer_humidity").state == STATE_UNAVAILABLE
    # Its battery is still a real reading.
    assert hass.states.get("sensor.chest_freezer_battery").state == "18"
    # Beverage Fridge has real readings (humidity is unit-agnostic).
    assert (
        hass.states.get("sensor.beverage_fridge_temperature").state != STATE_UNAVAILABLE
    )
    assert hass.states.get("sensor.beverage_fridge_humidity").state == "51.0"


async def test_spuck_last_call_in(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Each SPuck exposes its last call-in as a timestamp sensor."""
    await _setup(hass, mock_config_entry)
    # CallinTime is parsed as UTC (no offset applied).
    assert (
        hass.states.get("sensor.chest_freezer_last_call_in").state
        == "2025-04-05T06:47:31+00:00"
    )
    assert (
        hass.states.get("sensor.beverage_fridge_last_call_in").state
        == "2024-11-27T03:21:26+00:00"
    )


async def test_request_reading_button(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Pressing the button calls force-update for that gateway, then refreshes."""
    await _setup(hass, mock_config_entry)
    button = hass.states.get("button.warehouse_request_reading")
    assert button is not None

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.warehouse_request_reading"},
        blocking=True,
    )
    mock_client.async_force_update.assert_awaited_once_with("350000000000002")


async def test_request_reading_delayed_refresh(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """A press schedules a refresh a few seconds later (after the gateway calls in)."""
    await _setup(hass, mock_config_entry)
    before = mock_client.async_get_gateways.call_count

    # Press twice: the second press cancels the first pending refresh.
    for _ in range(2):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.warehouse_request_reading"},
            blocking=True,
        )
    # No refresh yet — it's scheduled for later.
    assert mock_client.async_get_gateways.call_count == before

    async_fire_time_changed(
        hass, dt_util.utcnow() + FORCE_UPDATE_SETTLE + timedelta(seconds=5)
    )
    await hass.async_block_till_done()
    assert mock_client.async_get_gateways.call_count > before


async def test_pending_refresh_canceled_on_unload(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Unloading cancels a button's pending post-press refresh."""
    await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.warehouse_request_reading"},
        blocking=True,
    )
    before = mock_client.async_get_gateways.call_count

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    async_fire_time_changed(
        hass, dt_util.utcnow() + FORCE_UPDATE_SETTLE + timedelta(seconds=5)
    )
    await hass.async_block_till_done()
    # The canceled refresh never fired.
    assert mock_client.async_get_gateways.call_count == before


async def test_request_reading_button_error(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """A failed force-update surfaces as a HomeAssistantError to the user."""
    from custom_components.sensoredlife.api import SensoredLifeConnectionError

    await _setup(hass, mock_config_entry)
    mock_client.async_force_update = AsyncMock(side_effect=SensoredLifeConnectionError)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.warehouse_request_reading"},
            blocking=True,
        )


async def test_dynamic_devices(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    devices_payload,
) -> None:
    """A gateway added to the account after setup appears without a reload."""
    from custom_components.sensoredlife.models import parse_devices

    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.new_site_temperature") is None

    extra = [
        *devices_payload,
        {
            "Name": "New Site",
            "IMEI": "999000111",
            "DeviceId": "999000111",
            "SerialNumber": "NEW123",
            "BatteryVoltage": "4.10",
            "LastRead": {
                "Temperature": "70.0",
                "Humidity": "40.0",
                "Power": "1.00",
                "SignalStrength": "25",
                "ReportTimestamp": "2026-06-08 03:00:00",
            },
            "AlarmPoints": [
                {
                    "PeripheralId": None,
                    "DeviceSensor": {"SensorType": "TEMP"},
                    "RangeMin": 40,
                    "RangeMax": 85,
                },
            ],
            "Peripherals": [],
        },
    ]
    mock_client.async_get_gateways = AsyncMock(return_value=parse_devices(extra))
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.new_site_temperature") is not None
    assert hass.states.get("button.new_site_request_reading") is not None


async def _refresh_with(
    hass: HomeAssistant, mock_client, entry: MockConfigEntry, payload: list
) -> None:
    """Point the mocked client at a payload and run one coordinator refresh."""
    from custom_components.sensoredlife.models import parse_devices

    mock_client.async_get_gateways = AsyncMock(return_value=parse_devices(payload))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_stale_devices(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    devices_payload,
) -> None:
    """A gateway missing from 3 consecutive polls is dropped from the registry."""
    await _setup(hass, mock_config_entry)
    registry = dr.async_get(hass)
    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")})

    reduced = [d for d in devices_payload if d["IMEI"] != "350000000000002"]
    for _ in range(3):
        await _refresh_with(hass, mock_client, mock_config_entry, reduced)

    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")}) is None
    # A surviving gateway stays.
    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000001")})


async def test_transient_absence_not_pruned(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    devices_payload,
) -> None:
    """One or two polls missing (a transient partial response) prune nothing."""
    await _setup(hass, mock_config_entry)
    registry = dr.async_get(hass)

    reduced = [d for d in devices_payload if d["IMEI"] != "350000000000002"]
    for _ in range(2):
        await _refresh_with(hass, mock_client, mock_config_entry, reduced)
        assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")})

    # The full roster returns — the miss streak resets…
    await _refresh_with(hass, mock_client, mock_config_entry, devices_payload)
    # …so two MORE misses still don't reach the 3-consecutive threshold.
    for _ in range(2):
        await _refresh_with(hass, mock_client, mock_config_entry, reduced)
    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")})
    assert hass.states.get("sensor.warehouse_temperature") is not None


async def test_pruned_device_reappears(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    devices_payload,
) -> None:
    """A pruned device that returns to the roster gets device + entities back."""
    await _setup(hass, mock_config_entry)
    registry = dr.async_get(hass)
    assert hass.states.get("sensor.warehouse_temperature") is not None

    reduced = [d for d in devices_payload if d["IMEI"] != "350000000000002"]
    for _ in range(3):
        await _refresh_with(hass, mock_client, mock_config_entry, reduced)
    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")}) is None
    assert hass.states.get("sensor.warehouse_temperature") is None

    # The gateway reappears in the account — no restart needed.
    await _refresh_with(hass, mock_client, mock_config_entry, devices_payload)
    assert registry.async_get_device(identifiers={(DOMAIN, "350000000000002")})
    temp = hass.states.get("sensor.warehouse_temperature")
    assert temp is not None
    assert temp.state != STATE_UNAVAILABLE
    assert hass.states.get("button.warehouse_request_reading") is not None


async def test_single_auth_glitch_no_reauth(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """One auth failure after a working poll is damped to UpdateFailed."""
    await _setup(hass, mock_config_entry)

    mock_client.async_get_gateways = AsyncMock(side_effect=SensoredLifeAuthError)
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    coordinator = mock_config_entry.runtime_data
    assert coordinator.last_update_success is False
    # No reauth flow was started for a single (possibly transient) failure.
    assert not [
        f
        for f in hass.config_entries.flow.async_progress()
        if f["context"]["source"] == "reauth"
    ]


async def test_second_consecutive_auth_failure_reauths(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Two consecutive auth failures start the reauthentication flow."""
    await _setup(hass, mock_config_entry)

    mock_client.async_get_gateways = AsyncMock(side_effect=SensoredLifeAuthError)
    for _ in range(2):
        await mock_config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


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
