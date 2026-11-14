"""Service handlers for the Incus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ACTION_FREEZE,
    ACTION_RESTART,
    ACTION_START,
    ACTION_STOP,
    ACTION_UNFREEZE,
    ATTR_ENTRY_ID,
    ATTR_FORCE,
    ATTR_INSTANCE,
    ATTR_PROJECT,
    ATTR_TIMEOUT,
    DOMAIN,
    SERVICE_FREEZE_INSTANCE,
    SERVICE_REFRESH,
    SERVICE_RESTART_INSTANCE,
    SERVICE_START_INSTANCE,
    SERVICE_STOP_INSTANCE,
    SERVICE_UNFREEZE_INSTANCE,
)
from .coordinator import IncusCoordinator
from .incus_client import IncusError

_LOGGER = logging.getLogger(__name__)

INSTANCE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_INSTANCE): cv.string,
        vol.Optional(ATTR_PROJECT): cv.string,
        vol.Optional(ATTR_FORCE, default=False): cv.boolean,
        vol.Optional(ATTR_TIMEOUT, default=60): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=3600)
        ),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

REFRESH_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

# Map service name -> Incus state action.
_SERVICE_ACTIONS = {
    SERVICE_START_INSTANCE: ACTION_START,
    SERVICE_STOP_INSTANCE: ACTION_STOP,
    SERVICE_RESTART_INSTANCE: ACTION_RESTART,
    SERVICE_FREEZE_INSTANCE: ACTION_FREEZE,
    SERVICE_UNFREEZE_INSTANCE: ACTION_UNFREEZE,
}


def _async_get_coordinators(
    hass: HomeAssistant, entry_id: str | None = None
) -> list[IncusCoordinator]:
    """Return the coordinators of all loaded (or one specific) entries."""
    entries: list[ConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id is not None:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    coordinators: list[IncusCoordinator] = []
    for entry in entries:
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            coordinators.append(coordinator)
    return coordinators


async def _async_handle_instance_action(
    hass: HomeAssistant,
    action: str,
    data: dict[str, Any],
) -> None:
    """Handle a start/stop/restart/freeze/unfreeze service call."""
    coordinators = _async_get_coordinators(hass, data.get(ATTR_ENTRY_ID))
    if not coordinators:
        raise HomeAssistantError("No Incus integration is configured")

    name: str = data[ATTR_INSTANCE]
    project: str | None = data.get(ATTR_PROJECT)
    force: bool = data.get(ATTR_FORCE, False)
    timeout: int = data.get(ATTR_TIMEOUT, 60)

    matched = False
    last_error: Exception | None = None
    for coordinator in coordinators:
        instance = coordinator.find_instance(name, project)
        if instance is None:
            continue
        matched = True
        try:
            await coordinator.async_instance_action(
                instance.name,
                action,
                project=instance.project,
                force=force,
                timeout=timeout,
            )
        except IncusError as err:
            last_error = err
            _LOGGER.error("Failed to %s instance %s: %s", action, instance.name, err)

    if not matched:
        raise HomeAssistantError(f"Instance '{name}' was not found on any Incus server")

    if last_error is not None:
        raise HomeAssistantError(
            f"Unable to {action} instance '{name}': {last_error}"
        ) from last_error


async def _async_handle_refresh(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Handle the refresh service call."""
    coordinators = _async_get_coordinators(hass, data.get(ATTR_ENTRY_ID))
    if not coordinators:
        raise HomeAssistantError("No Incus integration is configured")

    for coordinator in coordinators:
        await coordinator.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Incus services (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    for service_name, action in _SERVICE_ACTIONS.items():

        async def _handler(call: ServiceCall, action: str = action) -> None:
            await _async_handle_instance_action(hass, action, dict(call.data))

        hass.services.async_register(
            DOMAIN,
            service_name,
            _handler,
            schema=INSTANCE_SERVICE_SCHEMA,
        )

    async def _refresh_handler(call: ServiceCall) -> None:
        await _async_handle_refresh(hass, dict(call.data))

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _refresh_handler,
        schema=REFRESH_SERVICE_SCHEMA,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the Incus services when the last entry is unloaded."""
    if hass.config_entries.async_loaded_entries(DOMAIN):
        return
    for service_name in (*_SERVICE_ACTIONS, SERVICE_REFRESH):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
