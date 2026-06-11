"""Parsed data models for the SensoredLife integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from .const import (
    SPUCK_HUMID_SENTINELS,
    SPUCK_TEMP_SENTINELS,
    STALE_AFTER,
)

# The cloud JSON is untyped, so the parsing helpers accept Any and coerce
# defensively (missing keys, strings, nulls all degrade to None).
type Json = dict[str, Any]


def _drop_sentinel(value: float | None, sentinels: tuple[float, ...]) -> float | None:
    """Map a no-reading sentinel to None; pass real readings through.

    The cloud sends sentinels as the exact strings "999.90" / "99.90", so
    compare exactly after rounding to one decimal — a tolerance window would
    also swallow REAL readings near a sentinel (e.g. 99.4–100.4 %RH).
    """
    if value is None:
        return None
    if round(value, 1) in sentinels:
        return None
    return value


def _to_float(value: Any) -> float | None:
    """Coerce a value to a rounded float, or None if it isn't numeric."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _parse_ts(raw: Any) -> datetime | None:
    """Parse a 'YYYY-MM-DD HH:MM:SS' cloud timestamp as aware UTC.

    The cloud reports ReportTimestamp / CallinTime in UTC (verified against the
    site's own "N minutes ago" display); the device's ``Timezone`` field is only
    a display preference and must NOT be applied here.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return naive.replace(tzinfo=UTC)


@dataclass(slots=True)
class SafeRange:
    """A configured safe (alarm) range for a sensor."""

    minimum: float | None
    maximum: float | None

    def contains(self, value: float | None) -> bool | None:
        """Whether value is within the range; None if undetermined."""
        if value is None or self.minimum is None or self.maximum is None:
            return None
        return self.minimum <= value <= self.maximum


@dataclass(slots=True)
class Spuck:
    """A wireless SPuck sub-probe attached to a gateway."""

    spuck_id: str
    gateway_imei: str
    name: str
    battery_level: int | None
    signal_strength: float | None
    temperature: float | None
    temperature_range: SafeRange
    humidity: float | None
    humidity_range: SafeRange
    last_callin: datetime | None

    @classmethod
    def from_json(cls, gateway_imei: str, raw: Json) -> Spuck:
        temp, t_lo, t_hi = _reading(raw.get("AlarmPoints"), "SP_TEMP")
        hum, h_lo, h_hi = _reading(raw.get("AlarmPoints"), "SP_HUMID")
        temp = _drop_sentinel(temp, SPUCK_TEMP_SENTINELS)
        hum = _drop_sentinel(hum, SPUCK_HUMID_SENTINELS)
        # The API sends numbers as strings, so coerce like every other reading
        # (a string "18" would otherwise silently parse to None). Non-finite
        # values (float() accepts "inf"/"nan") stay garbage -> None.
        battery = _to_float(raw.get("BatteryLevel"))
        return cls(
            spuck_id=str(raw.get("Id")),
            gateway_imei=gateway_imei,
            name=str(raw.get("Name") or raw.get("Id") or "SPuck"),
            battery_level=int(battery)
            if battery is not None and isfinite(battery)
            else None,
            signal_strength=_to_float(raw.get("SignalStrength")),
            temperature=temp,
            temperature_range=SafeRange(t_lo, t_hi),
            humidity=hum,
            humidity_range=SafeRange(h_lo, h_hi),
            last_callin=_parse_ts(raw.get("CallinTime")),
        )


@dataclass(slots=True)
class Gateway:
    """A MarCELL cellular gateway and its current readings."""

    imei: str
    name: str
    location: str | None
    serial_number: str | None
    firmware: str | None
    temperature: float | None
    temperature_range: SafeRange
    humidity: float | None
    humidity_range: SafeRange
    power_on: bool | None
    signal_strength: float | None
    battery_voltage: float | None
    last_report: datetime | None
    spucks: list[Spuck] = field(default_factory=list)

    @property
    def online(self) -> bool | None:
        """Whether the most recent cloud read is recent enough."""
        if self.last_report is None:
            return None
        return (datetime.now(UTC) - self.last_report) <= STALE_AFTER

    @classmethod
    def from_json(cls, raw: Json) -> Gateway:
        imei = str(raw.get("IMEI") or raw.get("DeviceId"))
        last = raw.get("LastRead") or {}
        t_lo, t_hi = _device_range(raw, "TEMP")
        h_lo, h_hi = _device_range(raw, "HUMIDITY")
        power = _to_float(last.get("Power"))
        signal = _to_float(last.get("SignalStrength"))
        if signal is None:
            signal = _to_float(raw.get("SignalStrength"))
        gateway = cls(
            imei=imei,
            name=str(raw.get("Name") or raw.get("SerialNumber") or "MarCELL"),
            location=raw.get("Location"),
            serial_number=raw.get("SerialNumber"),
            firmware=raw.get("FirmwareVersion"),
            temperature=_to_float(last.get("Temperature")),
            temperature_range=SafeRange(t_lo, t_hi),
            humidity=_to_float(last.get("Humidity")),
            humidity_range=SafeRange(h_lo, h_hi),
            power_on=None if power is None else power >= 0.5,
            signal_strength=signal,
            battery_voltage=_to_float(raw.get("BatteryVoltage")),
            last_report=_parse_ts(last.get("ReportTimestamp")),
        )
        gateway.spucks = [
            Spuck.from_json(imei, sp) for sp in (raw.get("Peripherals") or [])
        ]
        return gateway


def _device_range(raw: Json, sensor_type: str) -> tuple[float | None, float | None]:
    """(min, max) for a device-level AlarmPoint (PeripheralId is None).

    The API sends numbers as strings, so the bounds are coerced like every
    other reading — SafeRange.contains would otherwise compare str to float.
    """
    for ap in raw.get("AlarmPoints") or []:
        if ap.get("PeripheralId"):
            continue
        sensor = ap.get("DeviceSensor") or {}
        if sensor.get("SensorType") == sensor_type:
            return _to_float(ap.get("RangeMin")), _to_float(ap.get("RangeMax"))
    return None, None


def _reading(
    alarm_points: Any, sensor_type: str
) -> tuple[float | None, float | None, float | None]:
    """(value, min, max) from a SPuck AlarmPoint of the given SensorType."""
    for ap in alarm_points or []:
        sensor = ap.get("DeviceSensor") or {}
        if sensor.get("SensorType") == sensor_type:
            return (
                _to_float(ap.get("LastRead")),
                _to_float(ap.get("RangeMin")),
                _to_float(ap.get("RangeMax")),
            )
    return None, None, None


def parse_devices(payload: list[Any]) -> dict[str, Gateway]:
    """Parse the /devices response into a mapping of IMEI -> Gateway."""
    gateways: dict[str, Gateway] = {}
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        gateway = Gateway.from_json(raw)
        gateways[gateway.imei] = gateway
    return gateways
