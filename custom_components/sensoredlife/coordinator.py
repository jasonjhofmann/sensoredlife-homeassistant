"""DataUpdateCoordinator for the SensoredLife integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
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
        # of Home Assistant's shared session. HA owns its lifecycle (closed at
        # shutdown) — calling session.close() ourselves is blocked by core's
        # warn_use wrapper as of HA 2026.5+.
        session = async_create_clientsession(hass)
        self.client = SensoredLifeClient(
            session,
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> dict[str, Gateway]:
        """Fetch the latest readings for every gateway."""
        try:
            data = await self.client.async_get_gateways()
        except SensoredLifeAuthError as err:
            # Surfaced to HA → starts the reauthentication flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except SensoredLifeConnectionError as err:
            raise UpdateFailed(str(err)) from err
        _LOGGER.debug(
            "Poll OK: %d gateways (%s)",
            len(data),
            ", ".join(gateway.name for gateway in data.values()) or "none",
        )
        self._async_remove_stale_devices(data)
        return data

    @callback
    def _async_remove_stale_devices(self, data: dict[str, Gateway]) -> None:
        """Drop devices (gateways/SPucks) no longer present in the account.

        The /devices feed is the full account roster (offline devices still
        appear), so a missing identifier means the device was genuinely removed.
        """
        # Never prune on an empty roster — a spurious empty response would
        # otherwise wipe every device (and detach its history).
        if not data:
            return

        current: set[str] = set()
        for imei, gateway in data.items():
            current.add(imei)
            current.update(spuck.spuck_id for spuck in gateway.spucks)

        device_registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            ids = {ident for domain, ident in device.identifiers if domain == DOMAIN}
            if ids and ids.isdisjoint(current):
                _LOGGER.info(
                    "Removing stale device %s — no longer in the account roster",
                    device.name,
                )
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=self.config_entry.entry_id
                )
