"""The Incus integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_CA_CERT,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PORT,
    CONF_SOCKET_PATH,
    CONF_VERIFY_SSL,
    CONNECTION_TLS,
    CONNECTION_UNIX,
    DEFAULT_PORT,
    DEFAULT_SOCKET_PATH,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import IncusCoordinator
from .incus_client import (
    IncusAuthError,
    IncusClient,
    IncusConnectionParams,
    IncusError,
)
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "PLATFORMS", "async_setup_entry", "async_unload_entry"]


def build_connection_params(entry: ConfigEntry) -> IncusConnectionParams:
    """Create connection parameters from a config entry."""
    data = entry.data

    if data.get(CONF_CONNECTION_TYPE) == CONNECTION_UNIX:
        return IncusConnectionParams(
            connection_type=CONNECTION_UNIX,
            socket_path=data.get(CONF_SOCKET_PATH, DEFAULT_SOCKET_PATH),
        )

    return IncusConnectionParams(
        connection_type=CONNECTION_TLS,
        host=data.get(CONF_HOST),
        port=data.get(CONF_PORT, DEFAULT_PORT),
        verify_ssl=data.get(CONF_VERIFY_SSL, True),
        client_cert=data.get(CONF_CLIENT_CERT) or None,
        client_key=data.get(CONF_CLIENT_KEY) or None,
        ca_cert=data.get(CONF_CA_CERT) or None,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Incus from a config entry."""
    params = build_connection_params(entry)
    client = IncusClient(params)

    # Always close the HTTP client when the entry is unloaded. Home Assistant
    # also runs the on-unload callbacks when setup fails, so this covers the
    # failure paths below as well.
    entry.async_on_unload(client.close)

    try:
        await client.async_connect()
        await client.async_get_server()
    except IncusAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IncusError as err:
        raise ConfigEntryNotReady(f"Unable to connect to Incus: {err}") from err

    coordinator = IncusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    # Create the hub (server) device before the platforms run so that the
    # instance/volume/pool devices can reference it through ``via_device_id``.
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Incus",
        manufacturer=MANUFACTURER,
        model="Incus Server",
        configuration_url=coordinator.configuration_url,
    )
    coordinator.hub_device_id = device.id

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Incus config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data = None
        await async_unload_services(hass)

    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
