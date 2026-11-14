"""Switch platform for the Incus integration.

The switch exposes the power state of an instance: turning it on starts the
instance, turning it off stops it. Start/stop/restart are also available as
dedicated buttons and services.
"""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_START, ACTION_STOP
from .coordinator import IncusCoordinator, InstanceData
from .entity import EntityDiscoverer, IncusInstanceEntity
from .incus_client import IncusError


class IncusInstanceSwitch(IncusInstanceEntity, SwitchEntity):
    """A switch that represents the running state of an Incus instance."""

    _attr_icon = "mdi:server"

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        instance: InstanceData,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, entry, instance)
        self._attr_name = "Power"
        self._attr_unique_id = f"{entry.entry_id}_{instance.key}_power"

    @property
    def is_on(self) -> bool | None:
        """Return True when the instance is running."""
        instance = self.instance
        if instance is None:
            return None
        return instance.is_active

    async def async_turn_on(self, **kwargs) -> None:
        """Start the instance."""
        await self._async_set_power(ACTION_START)

    async def async_turn_off(self, **kwargs) -> None:
        """Stop the instance."""
        await self._async_set_power(ACTION_STOP)

    async def _async_set_power(self, action: str) -> None:
        instance = self.instance
        if instance is None:
            raise HomeAssistantError("The instance is no longer available")
        try:
            await self.coordinator.async_instance_action(
                instance.name,
                action,
                project=instance.project,
                timeout=60,
            )
        except IncusError as err:
            raise HomeAssistantError(
                f"Unable to {action} instance {instance.name}: {err}"
            ) from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Incus switches."""
    coordinator: IncusCoordinator = entry.runtime_data

    discoverer = EntityDiscoverer(
        hass,
        coordinator,
        async_add_entities,
        items_fn=lambda data: data.instances.values(),
        key_fn=lambda instance: instance.key,
        factory=lambda instance: [IncusInstanceSwitch(coordinator, entry, instance)],
    )
    discoverer()
    entry.async_on_unload(coordinator.async_add_listener(discoverer))
