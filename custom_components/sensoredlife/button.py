"""Button platform for the SensoredLife integration."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SensoredLifeError
from .const import DOMAIN
from .coordinator import SensoredLifeConfigEntry, SensoredLifeCoordinator
from .entity import EntitySpec, GatewayEntity, add_entities_for_devices

# Force-update presses go to the cloud serially — one credit-spending call at a
# time rather than a burst.
PARALLEL_UPDATES = 1

REQUEST_READING = ButtonEntityDescription(
    key="request_reading",
    translation_key="request_reading",
    icon="mdi:cloud-sync",
)


def _build(coordinator: SensoredLifeCoordinator) -> Iterable[EntitySpec]:
    for imei in coordinator.data:
        yield (
            f"{imei}_request_reading",
            partial(SensoredLifeRequestReadingButton, coordinator, imei),
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensoredLifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SensoredLife buttons from a config entry."""
    add_entities_for_devices(entry, async_add_entities, _build)


class SensoredLifeRequestReadingButton(GatewayEntity, ButtonEntity):
    """Asks a gateway to call in now (the website's "Update" button)."""

    entity_description = REQUEST_READING

    def __init__(self, coordinator: SensoredLifeCoordinator, imei: str) -> None:
        """Initialize the request-reading button."""
        super().__init__(coordinator, imei)
        self._attr_unique_id = f"{imei}_request_reading"

    async def async_press(self) -> None:
        """Trigger an on-demand reading, then refresh once the cloud catches up."""
        gateway = self.gateway
        name = gateway.name if gateway else self._imei
        try:
            await self.coordinator.client.async_force_update(self._imei)
        except SensoredLifeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="force_update_failed",
                translation_placeholders={"name": name, "error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
