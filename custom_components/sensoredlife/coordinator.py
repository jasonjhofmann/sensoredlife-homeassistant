"""DataUpdateCoordinator for the SensoredLife integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SensoredLifeAuthError,
    SensoredLifeClient,
    SensoredLifeConnectionError,
)
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .models import Gateway

_LOGGER = logging.getLogger(__name__)

type SensoredLifeConfigEntry = ConfigEntry[SensoredLifeCoordinator]


class SensoredLifeCoordinator(DataUpdateCoordinator[dict[str, Gateway]]):
    """Polls the SensoredLife cloud cache and exposes parsed gateways."""

    config_entry: SensoredLifeConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: SensoredLifeConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        # A dedicated session (own cookie jar) keeps the login XSRF cookie out
        # of Home Assistant's shared session; closed when the entry unloads.
        session = async_create_clientsession(hass)
        config_entry.async_on_unload(session.close)
        self.client = SensoredLifeClient(
            session,
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> dict[str, Gateway]:
        """Fetch the latest readings for every gateway."""
        try:
            return await self.client.async_get_gateways()
        except SensoredLifeAuthError as err:
            # Surfaced to HA → starts the reauthentication flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except SensoredLifeConnectionError as err:
            raise UpdateFailed(str(err)) from err
