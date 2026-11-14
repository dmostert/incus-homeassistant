"""The Incus integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

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

    try:
        await client.async_connect()
        await client.async_get_server()
    except IncusAuthError as err:
        await client.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except IncusError as err:
        await client.close()
        raise ConfigEntryNotReady(f"Unable to connect to Incus: {err}") from err

    coordinator = IncusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Incus config entry."""
    coordinator: IncusCoordinator | None = entry.runtime_data

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        if coordinator is not None:
            await coordinator.client.close()
        entry.runtime_data = None
        await async_unload_services(hass)

    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
