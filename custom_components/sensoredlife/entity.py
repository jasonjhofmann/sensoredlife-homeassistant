"""Base entities for the SensoredLife integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SensoredLifeCoordinator
from .models import Gateway, Spuck


class GatewayEntity(CoordinatorEntity[SensoredLifeCoordinator]):
    """Base entity bound to a MarCELL gateway."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SensoredLifeCoordinator, imei: str) -> None:
        """Initialize the gateway entity."""
        super().__init__(coordinator)
        self._imei = imei

    @property
    def gateway(self) -> Gateway | None:
        """The current gateway data, or None if it dropped out of the feed."""
        return self.coordinator.data.get(self._imei)

    @property
    def available(self) -> bool:
        """Available while the coordinator succeeds and the gateway is present."""
        return super().available and self.gateway is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry for the gateway."""
        gateway = self.gateway
        return DeviceInfo(
            identifiers={(DOMAIN, self._imei)},
            manufacturer=MANUFACTURER,
            model="MarCELL PRO",
            name=gateway.name if gateway else self._imei,
            serial_number=gateway.serial_number if gateway else None,
            sw_version=gateway.firmware if gateway else None,
        )


class SpuckEntity(CoordinatorEntity[SensoredLifeCoordinator]):
    """Base entity bound to a wireless SPuck, parented to its gateway."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SensoredLifeCoordinator, imei: str, spuck_id: str
    ) -> None:
        """Initialize the SPuck entity."""
        super().__init__(coordinator)
        self._imei = imei
        self._spuck_id = spuck_id

    @property
    def spuck(self) -> Spuck | None:
        """The current SPuck data, or None if it dropped out of the feed."""
        gateway = self.coordinator.data.get(self._imei)
        if gateway is None:
            return None
        for spuck in gateway.spucks:
            if spuck.spuck_id == self._spuck_id:
                return spuck
        return None

    @property
    def available(self) -> bool:
        """Available while the coordinator succeeds and the SPuck is present."""
        return super().available and self.spuck is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry for the SPuck, linked to its gateway."""
        spuck = self.spuck
        return DeviceInfo(
            identifiers={(DOMAIN, self._spuck_id)},
            manufacturer=MANUFACTURER,
            model="SPuck",
            name=spuck.name if spuck else self._spuck_id,
            via_device=(DOMAIN, self._imei),
        )
