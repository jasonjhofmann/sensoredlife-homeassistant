"""Tests for the SensoredLife data models (pure parsing logic)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.sensoredlife.models import (
    SafeRange,
    _to_float,
    parse_devices,
)


def test_parse_devices(devices_payload) -> None:
    """Gateways and SPucks parse with correct values and units."""
    gateways = parse_devices(devices_payload)
    assert set(gateways) == {"350000000000001", "350000000000002"}

    wine = gateways["350000000000001"]
    assert wine.name == "Wine Cellar"
    assert wine.temperature == 58.8
    assert wine.humidity == 31.9
    assert wine.power_on is True
    assert wine.signal_strength == 32.0
    assert wine.battery_voltage == 4.09
    assert wine.temperature_range.contains(wine.temperature) is True
    # ReportTimestamp is UTC; the device Timezone field is not applied.
    assert wine.last_report == datetime(2026, 6, 8, 2, 10, 33, tzinfo=UTC)
    assert len(wine.spucks) == 2


def test_spuck_sentinels_become_none(devices_payload) -> None:
    """SPuck 999.9/99.9 sentinels parse to None (offline)."""
    gateways = parse_devices(devices_payload)
    spucks = {s.name: s for s in gateways["350000000000001"].spucks}

    offline = spucks["Chest Freezer"]
    assert offline.temperature is None
    assert offline.humidity is None
    assert offline.battery_level == 18

    live = spucks["Beverage Fridge"]
    assert live.temperature == 59.1
    assert live.humidity == 51.0
    assert live.temperature_range.contains(live.temperature) is True


def test_temp_sentinel_99_9() -> None:
    """A leak-only puck reports 99.9 for both temp and humidity -> None (N/A)."""
    gateways = parse_devices(
        [
            {
                "Name": "Garage",
                "IMEI": "111",
                "LastRead": {},
                "AlarmPoints": [],
                "Peripherals": [
                    {
                        "Id": "AAAA",
                        "Name": "Leak Puck",
                        "BatteryLevel": 11,
                        "AlarmPoints": [
                            {
                                "DeviceSensor": {"SensorType": "SP_TEMP"},
                                "LastRead": "99.90",
                            },
                            {
                                "DeviceSensor": {"SensorType": "SP_HUMID"},
                                "LastRead": "99.90",
                            },
                        ],
                    }
                ],
            }
        ]
    )
    spuck = gateways["111"].spucks[0]
    assert spuck.temperature is None
    assert spuck.humidity is None
    assert spuck.battery_level == 11


def test_string_battery_level_coerced() -> None:
    """A string BatteryLevel (as the API sends numbers) coerces to int."""
    gateways = parse_devices(
        [
            {
                "Name": "Garage",
                "IMEI": "333",
                "LastRead": {},
                "AlarmPoints": [],
                "Peripherals": [
                    {"Id": "CCCC", "Name": "String Batt", "BatteryLevel": "18"},
                    {"Id": "DDDD", "Name": "Garbage Batt", "BatteryLevel": "inf"},
                    {"Id": "EEEE", "Name": "No Batt", "BatteryLevel": None},
                ],
            }
        ]
    )
    spucks = {s.name: s for s in gateways["333"].spucks}
    assert spucks["String Batt"].battery_level == 18
    # Garbage (non-numeric or non-finite) still degrades to None.
    assert spucks["Garbage Batt"].battery_level is None
    assert spucks["No Batt"].battery_level is None


def test_out_of_range(devices_payload) -> None:
    """A reading outside its safe band reports in_safe_range False."""
    gateways = parse_devices(devices_payload)
    warehouse = gateways["350000000000002"]
    assert warehouse.temperature == 81.3
    assert warehouse.temperature_range.contains(81.3) is False
    assert warehouse.spucks == []


def test_string_alarm_point_bounds_coerced() -> None:
    """String RangeMin/RangeMax (as the API sends them) coerce to floats."""
    gateways = parse_devices(
        [
            {
                "Name": "Cellar",
                "IMEI": "222",
                "LastRead": {"Temperature": "58.80"},
                "AlarmPoints": [
                    {
                        "PeripheralId": None,
                        "DeviceSensor": {"SensorType": "TEMP"},
                        "RangeMin": "40",
                        "RangeMax": "85",
                    },
                ],
                "Peripherals": [
                    {
                        "Id": "BBBB",
                        "Name": "Probe",
                        "BatteryLevel": 50,
                        "AlarmPoints": [
                            {
                                "DeviceSensor": {"SensorType": "SP_TEMP"},
                                "LastRead": "59.10",
                                "RangeMin": "53.0",
                                "RangeMax": "66.0",
                            },
                        ],
                    }
                ],
            }
        ]
    )
    gateway = gateways["222"]
    assert gateway.temperature_range.minimum == 40.0
    assert gateway.temperature_range.maximum == 85.0
    # contains() no longer blows up comparing str bounds to a float reading.
    assert gateway.temperature_range.contains(gateway.temperature) is True
    spuck = gateway.spucks[0]
    assert spuck.temperature_range.minimum == 53.0
    assert spuck.temperature_range.contains(spuck.temperature) is True


def test_sentinel_exact_match_only() -> None:
    """Sentinels match exactly; real readings near them are not masked."""
    gateways = parse_devices(
        [
            {
                "Name": "Edge",
                "IMEI": "333",
                "LastRead": {},
                "AlarmPoints": [],
                "Peripherals": [
                    {
                        "Id": "CCCC",
                        "Name": "Near Sentinel",
                        "AlarmPoints": [
                            {
                                "DeviceSensor": {"SensorType": "SP_TEMP"},
                                "LastRead": "100.40",
                            },
                            {
                                "DeviceSensor": {"SensorType": "SP_HUMID"},
                                "LastRead": "99.50",
                            },
                        ],
                    },
                    {
                        "Id": "DDDD",
                        "Name": "Offline",
                        "AlarmPoints": [
                            {
                                "DeviceSensor": {"SensorType": "SP_TEMP"},
                                "LastRead": "999.90",
                            },
                            {
                                "DeviceSensor": {"SensorType": "SP_HUMID"},
                                "LastRead": "99.90",
                            },
                        ],
                    },
                ],
            }
        ]
    )
    near, offline = gateways["333"].spucks
    # Real readings that the old ±0.5 tolerance window wrongly masked.
    assert near.temperature == 100.4
    assert near.humidity == 99.5
    # Exact sentinels still map to None.
    assert offline.temperature is None
    assert offline.humidity is None


def test_safe_range_undetermined() -> None:
    """A range missing a bound returns None (undetermined), not a crash."""
    assert SafeRange(None, 50).contains(20) is None
    assert SafeRange(10, 50).contains(None) is None
    assert SafeRange(10, 50).contains(30) is True


def test_parse_skips_non_dict_entries() -> None:
    """Malformed list entries are ignored rather than raising."""
    assert parse_devices([None, "junk", 42]) == {}


def test_bad_values_coerce_to_none() -> None:
    """Non-numeric readings and bad timestamps degrade gracefully."""
    gateways = parse_devices(
        [
            {
                "Name": "Broken",
                "IMEI": "000",
                "Timezone": "not-a-number",
                "BatteryVoltage": "n/a",
                "LastRead": {
                    "Temperature": "",
                    "Humidity": None,
                    "Power": "x",
                    "ReportTimestamp": "garbage",
                },
                "AlarmPoints": [],
                "Peripherals": [],
            }
        ]
    )
    g = gateways["000"]
    assert g.temperature is None
    assert g.humidity is None
    assert g.power_on is None
    assert g.battery_voltage is None
    assert g.last_report is None
    assert g.online is None


@pytest.mark.parametrize(
    "value",
    [
        "inf",
        "-inf",
        "nan",
        "Infinity",
        float("inf"),
        float("-inf"),
        float("nan"),
    ],
)
def test_to_float_rejects_non_finite(value) -> None:
    """Non-finite inputs (float() parses "inf"/"nan" strings) map to None."""
    assert _to_float(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("18", 18.0), (72.456, 72.46), (0, 0.0), (-3.5, -3.5)],
)
def test_to_float_accepts_finite(value, expected) -> None:
    """Normal numeric inputs still coerce and round as before."""
    assert _to_float(value) == expected


def test_non_finite_readings_degrade_to_none() -> None:
    """Non-finite cloud values never reach readings or range bounds."""
    gateways = parse_devices(
        [
            {
                "Name": "Haunted",
                "IMEI": "444",
                "BatteryVoltage": "nan",
                "LastRead": {
                    "Temperature": "inf",
                    "Humidity": "nan",
                    "Power": "-inf",
                    "SignalStrength": float("nan"),
                },
                "AlarmPoints": [
                    {
                        "PeripheralId": None,
                        "DeviceSensor": {"SensorType": "TEMP"},
                        "RangeMin": "-inf",
                        "RangeMax": "inf",
                    },
                ],
                "Peripherals": [],
            }
        ]
    )
    g = gateways["444"]
    assert g.temperature is None
    assert g.humidity is None
    assert g.power_on is None
    assert g.signal_strength is None
    assert g.battery_voltage is None
    assert g.temperature_range.minimum is None
    assert g.temperature_range.maximum is None
