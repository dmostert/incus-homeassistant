"""Diagnostics support for the Incus integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_CERT, CONF_CLIENT_KEY
from .coordinator import IncusCoordinator

TO_REDACT = {CONF_CLIENT_KEY, CONF_CLIENT_CERT}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: IncusCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "server": asdict(data.server) if data else None,
        "instances": [asdict(item) for item in data.instances.values()] if data else [],
        "volumes": [asdict(item) for item in data.volumes.values()] if data else [],
        "pools": [asdict(item) for item in data.pools.values()] if data else [],
    }
