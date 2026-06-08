"""Button platform for the SensoredLife integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SensoredLifeError
from .coordinator import SensoredLifeConfigEntry, SensoredLifeCoordinator
from .entity import GatewayEntity

# Force-update presses go to the cloud serially — one credit-spending call at a
# time rather than a burst.
PARALLEL_UPDATES = 1

REQUEST_READING = ButtonEntityDescription(
    key="request_reading",
    translation_key="request_reading",
    icon="mdi:cloud-sync",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensoredLifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SensoredLife buttons from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SensoredLifeRequestReadingButton(coordinator, imei) for imei in coordinator.data
    )


class SensoredLifeRequestReadingButton(GatewayEntity, ButtonEntity):
    """Asks a gateway to call in now (the website's "Update" button)."""

    entity_description = REQUEST_READING

    def __init__(self, coordinator: SensoredLifeCoordinator, imei: str) -> None:
        """Initialize the request-reading button."""
        super().__init__(coordinator, imei)
        self._attr_unique_id = f"{imei}_request_reading"

    async def async_press(self) -> None:
        """Trigger an on-demand reading, then refresh once the cloud catches up."""
        try:
            await self.coordinator.client.async_force_update(self._imei)
        except SensoredLifeError as err:
            raise HomeAssistantError(
                f"Failed to request a reading from {self._imei}: {err}"
            ) from err
        await self.coordinator.async_request_refresh()
