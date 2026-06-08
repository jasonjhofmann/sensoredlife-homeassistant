"""Binary sensor platform for the SensoredLife integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SensoredLifeConfigEntry, SensoredLifeCoordinator
from .entity import GatewayEntity
from .models import Gateway

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GatewayBinaryDescription(BinarySensorEntityDescription):
    """Describes a gateway binary sensor."""

    value_fn: Callable[[Gateway], bool | None]


GATEWAY_BINARY_SENSORS: tuple[GatewayBinaryDescription, ...] = (
    GatewayBinaryDescription(
        key="power",
        translation_key="power",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda g: g.power_on,
    ),
    GatewayBinaryDescription(
        key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda g: g.online,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensoredLifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SensoredLife binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SensoredLifeBinarySensor(coordinator, imei, desc)
        for imei in coordinator.data
        for desc in GATEWAY_BINARY_SENSORS
    )


class SensoredLifeBinarySensor(GatewayEntity, BinarySensorEntity):
    """A binary sensor on a MarCELL gateway (mains power / connectivity)."""

    entity_description: GatewayBinaryDescription

    def __init__(
        self,
        coordinator: SensoredLifeCoordinator,
        imei: str,
        description: GatewayBinaryDescription,
    ) -> None:
        """Initialize the gateway binary sensor."""
        super().__init__(coordinator, imei)
        self.entity_description = description
        self._attr_unique_id = f"{imei}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the current binary state."""
        if (gateway := self.gateway) is None:
            return None
        return self.entity_description.value_fn(gateway)
