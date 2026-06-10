"""Tests for SensoredLife diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensoredlife.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_credentials(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> None:
    """Diagnostics return gateway data with credentials and IDs redacted."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diag["entry"]["username"] == "**REDACTED**"
    assert diag["entry"]["password"] == "**REDACTED**"
    assert diag["last_update_success"] is True

    gateways = {g["name"]: g for g in diag["gateways"]}
    gateway = gateways["Wine Cellar"]
    # Identifiers are redacted (including the IMEI, which is no longer a key).
    assert gateway["serial_number"] == "**REDACTED**"
    assert gateway["imei"] == "**REDACTED**"
    # The parsed (lowercase) location is street-address-class data.
    assert gateway["location"] == "**REDACTED**"
    assert gateway["temperature"] == 58.8
    # The offline SPuck's sentinel readings are None in the parsed model.
    spucks = {s["name"]: s for s in gateway["spucks"]}
    assert spucks["Chest Freezer"]["temperature"] is None
    assert spucks["Chest Freezer"]["spuck_id"] == "**REDACTED**"
    assert spucks["Chest Freezer"]["gateway_imei"] == "**REDACTED**"


def test_redact_set_covers_raw_payload_keys() -> None:
    """Future-proofing: raw API payload keys scrub even though today's
    dump never includes raw payloads (guards against drift)."""
    from homeassistant.components.diagnostics import async_redact_data

    from custom_components.sensoredlife.diagnostics import TO_REDACT

    hypothetical_raw = {
        "IMEI": "350123456789012",
        "SerialNumber": "MC-1234",
        "DeviceId": 99,
        "PeripheralId": 7,
        "Id": 1234,
        "Location": "123 Main St",
        "AccessToken": "tok",
        "nested": [{"IMEI": "350000000000000"}],
        "Temperature": 58.8,  # non-sensitive keys survive
    }
    out = async_redact_data(hypothetical_raw, TO_REDACT)
    assert out["IMEI"] == "**REDACTED**"
    assert out["SerialNumber"] == "**REDACTED**"
    assert out["DeviceId"] == "**REDACTED**"
    assert out["PeripheralId"] == "**REDACTED**"
    assert out["Id"] == "**REDACTED**"
    assert out["Location"] == "**REDACTED**"
    assert out["AccessToken"] == "**REDACTED**"
    assert out["nested"][0]["IMEI"] == "**REDACTED**"
    assert out["Temperature"] == 58.8
