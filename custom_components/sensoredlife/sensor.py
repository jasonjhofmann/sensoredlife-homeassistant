"""Sensor platform for the SensoredLife integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SensoredLifeConfigEntry, SensoredLifeCoordinator
from .entity import EntitySpec, GatewayEntity, SpuckEntity, add_entities_for_devices
from .models import Gateway, SafeRange, Spuck

# All data comes from one coordinator refresh; no per-entity I/O.
PARALLEL_UPDATES = 0


def _range_attrs(value: float | None, safe: SafeRange) -> dict[str, Any]:
    return {
        "safe_minimum": safe.minimum,
        "safe_maximum": safe.maximum,
        "in_safe_range": safe.contains(value),
    }


@dataclass(frozen=True, kw_only=True)
class GatewaySensorDescription(SensorEntityDescription):
    """Describes a gateway sensor."""

    value_fn: Callable[[Gateway], float | datetime | None]
    attrs_fn: Callable[[Gateway], dict[str, Any]] | None = None
    available_fn: Callable[[Gateway], bool] = lambda _g: True


@dataclass(frozen=True, kw_only=True)
class SpuckSensorDescription(SensorEntityDescription):
    """Describes a SPuck sensor."""

    value_fn: Callable[[Spuck], float | int | None]
    attrs_fn: Callable[[Spuck], dict[str, Any]] | None = None
    # Whether a None reading should make the entity unavailable (offline probe)
    # rather than just report an empty value.
    unavailable_when_none: bool = False


GATEWAY_SENSORS: tuple[GatewaySensorDescription, ...] = (
    GatewaySensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda g: g.temperature,
        attrs_fn=lambda g: _range_attrs(g.temperature, g.temperature_range),
    ),
    GatewaySensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda g: g.humidity,
        attrs_fn=lambda g: _range_attrs(g.humidity, g.humidity_range),
    ),
    GatewaySensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:signal",
        value_fn=lambda g: g.signal_strength,
    ),
    GatewaySensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda g: g.battery_voltage,
    ),
    GatewaySensorDescription(
        key="last_read",
        translation_key="last_read",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda g: g.last_report,
    ),
)

SPUCK_SENSORS: tuple[SpuckSensorDescription, ...] = (
    SpuckSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature,
        attrs_fn=lambda s: _range_attrs(s.temperature, s.temperature_range),
        unavailable_when_none=True,
    ),
    SpuckSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.humidity,
        attrs_fn=lambda s: _range_attrs(s.humidity, s.humidity_range),
        unavailable_when_none=True,
    ),
    SpuckSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_level,
    ),
)


def _build(coordinator: SensoredLifeCoordinator) -> Iterable[EntitySpec]:
    for imei, gateway in coordinator.data.items():
        for desc in GATEWAY_SENSORS:
            yield (
                f"{imei}_{desc.key}",
                partial(SensoredLifeGatewaySensor, coordinator, imei, desc),
            )
        for spuck in gateway.spucks:
            for spuck_desc in SPUCK_SENSORS:
                yield (
                    f"{spuck.spuck_id}_{spuck_desc.key}",
                    partial(
                        SensoredLifeSpuckSensor,
                        coordinator,
                        imei,
                        spuck.spuck_id,
                        spuck_desc,
                    ),
                )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensoredLifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SensoredLife sensors from a config entry."""
    add_entities_for_devices(entry, async_add_entities, _build)


class SensoredLifeGatewaySensor(GatewayEntity, SensorEntity):
    """A sensor reading from a MarCELL gateway."""

    entity_description: GatewaySensorDescription

    def __init__(
        self,
        coordinator: SensoredLifeCoordinator,
        imei: str,
        description: GatewaySensorDescription,
    ) -> None:
        """Initialize the gateway sensor."""
        super().__init__(coordinator, imei)
        self.entity_description = description
        self._attr_unique_id = f"{imei}_{description.key}"

    @property
    def available(self) -> bool:
        """Available while the gateway is present and reports this value."""
        if not super().available or (gateway := self.gateway) is None:
            return False
        return self.entity_description.available_fn(gateway)

    @property
    def native_value(self) -> float | datetime | None:
        """Return the current value."""
        if (gateway := self.gateway) is None:
            return None
        return self.entity_description.value_fn(gateway)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return safe-range attributes when available."""
        if (
            gateway := self.gateway
        ) is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(gateway)


class SensoredLifeSpuckSensor(SpuckEntity, SensorEntity):
    """A sensor reading from a wireless SPuck."""

    entity_description: SpuckSensorDescription

    def __init__(
        self,
        coordinator: SensoredLifeCoordinator,
        imei: str,
        spuck_id: str,
        description: SpuckSensorDescription,
    ) -> None:
        """Initialize the SPuck sensor."""
        super().__init__(coordinator, imei, spuck_id)
        self.entity_description = description
        self._attr_unique_id = f"{spuck_id}_{description.key}"

    @property
    def available(self) -> bool:
        """Offline probes (sentinel reading) report as unavailable."""
        if not super().available or (spuck := self.spuck) is None:
            return False
        if self.entity_description.unavailable_when_none:
            return self.entity_description.value_fn(spuck) is not None
        return True

    @property
    def native_value(self) -> float | int | None:
        """Return the current value."""
        if (spuck := self.spuck) is None:
            return None
        return self.entity_description.value_fn(spuck)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return safe-range attributes when available."""
        if (spuck := self.spuck) is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(spuck)
