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

    gateway = diag["gateways"]["350000000000001"]
    assert gateway["name"] == "Wine Cellar"
    assert gateway["serial_number"] == "**REDACTED**"
    assert gateway["temperature"] == 58.8
    # The offline SPuck's sentinel readings are None in the parsed model.
    spucks = {s["name"]: s for s in gateway["spucks"]}
    assert spucks["Chest Freezer"]["temperature"] is None
