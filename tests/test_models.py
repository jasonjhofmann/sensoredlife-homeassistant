"""Tests for the SensoredLife data models (pure parsing logic)."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.sensoredlife.models import (
    SafeRange,
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
    # -8 offset: 02:10:33 local -> 10:10:33 UTC.
    assert wine.last_report == datetime(2026, 6, 8, 10, 10, 33, tzinfo=UTC)
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


def test_out_of_range(devices_payload) -> None:
    """A reading outside its safe band reports in_safe_range False."""
    gateways = parse_devices(devices_payload)
    warehouse = gateways["350000000000002"]
    assert warehouse.temperature == 81.3
    assert warehouse.temperature_range.contains(81.3) is False
    assert warehouse.spucks == []


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
