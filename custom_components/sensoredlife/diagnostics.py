"""Diagnostics support for the SensoredLife integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, CONF_USERNAME
from .coordinator import SensoredLifeConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "serial_number", "imei", "spuck_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SensoredLifeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    gateways = {
        imei: async_redact_data(asdict(gateway), TO_REDACT)
        for imei, gateway in coordinator.data.items()
    }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "gateways": async_redact_data(gateways, TO_REDACT),
    }
