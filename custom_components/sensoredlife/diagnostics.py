"""Diagnostics support for the SensoredLife integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, CONF_USERNAME
from .coordinator import SensoredLifeConfigEntry

# Keys redacted at any depth. Beyond the keys the dump contains TODAY
# (entry credentials + parsed snake_case identifiers), this pre-lists the
# sensitive keys of SensoredLife's RAW API payloads — the /devices roster
# (PascalCase) and the login response — which we never include today but
# would need scrubbing if a future revision attached a raw payload to the
# dump. async_redact_data matches dict keys at any depth, and unused keys
# cost nothing, so the superset is free insurance against drift.
TO_REDACT = {
    # Entry data
    CONF_USERNAME,
    CONF_PASSWORD,
    # Parsed-model identifier keys (present in today's dump). ``location`` is
    # street-address-class data, and async_redact_data is case-sensitive — the
    # PascalCase "Location" below only covers the raw payload form.
    "serial_number",
    "imei",
    "gateway_imei",
    "spuck_id",
    "location",
    # Raw /devices payload keys (hypothetical future inclusion)
    "IMEI",
    "SerialNumber",
    "DeviceId",
    "PeripheralId",
    "Id",
    "Location",
    # Raw login-response keys (hypothetical future inclusion)
    "AccessToken",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SensoredLifeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    # A list (not an IMEI-keyed dict) so the identifier isn't exposed as a key —
    # async_redact_data only redacts values, not dict keys.
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "update_interval": str(coordinator.update_interval),
        "last_update_success": coordinator.last_update_success,
        "last_exception": (
            str(coordinator.last_exception) if coordinator.last_exception else None
        ),
        "gateways": [
            async_redact_data(asdict(gateway), TO_REDACT)
            for gateway in coordinator.data.values()
        ],
    }
