"""Button platform for the Incus integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACTION_RESTART,
    ACTION_START,
    ACTION_STOP,
)
from .coordinator import IncusCoordinator, InstanceData
from .entity import EntityDiscoverer, IncusBaseEntity, IncusInstanceEntity
from .incus_client import IncusError


@dataclass(frozen=True, kw_only=True)
class IncusButtonDescription(ButtonEntityDescription):
    """Description of an instance action button."""

    action: str


INSTANCE_BUTTONS: tuple[IncusButtonDescription, ...] = (
    IncusButtonDescription(
        key="start",
        name="Start",
        icon="mdi:play",
        action=ACTION_START,
    ),
    IncusButtonDescription(
        key="stop",
        name="Stop",
        icon="mdi:stop",
        action=ACTION_STOP,
    ),
    IncusButtonDescription(
        key="restart",
        name="Restart",
        icon="mdi:restart",
        action=ACTION_RESTART,
    ),
)


class IncusInstanceButton(IncusInstanceEntity, ButtonEntity):
    """A button that performs an action on an Incus instance."""

    entity_description: IncusButtonDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        instance: InstanceData,
        description: IncusButtonDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, entry, instance)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{instance.key}_{description.key}"

    @property
    def available(self) -> bool:
        """Only show the button when the action makes sense."""
        if not super().available:
            return False
        instance = self.instance
        if instance is None:
            return False
        action = self.entity_description.action
        if action == ACTION_START:
            return not instance.is_active
        if action in (ACTION_STOP, ACTION_RESTART):
            return instance.is_active
        return True

    async def async_press(self) -> None:
        """Execute the instance action."""
        instance = self.instance
        if instance is None:
            raise HomeAssistantError("The instance is no longer available")

        action = self.entity_description.action
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


class IncusRefreshButton(IncusBaseEntity, ButtonEntity):
    """A button that forces a refresh of the Incus data."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: IncusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the refresh button."""
        super().__init__(coordinator, entry)
        self._attr_device_info = self.hub_device_info
        self._attr_unique_id = f"{entry.entry_id}_refresh"

    async def async_press(self) -> None:
        """Trigger a coordinator refresh.

        This re-reads the server and automatically discovers any new instances
        or storage volumes.
        """
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Incus buttons."""
    coordinator: IncusCoordinator = entry.runtime_data

    discoverer = EntityDiscoverer(
        hass,
        coordinator,
        async_add_entities,
        items_fn=lambda data: data.instances.values(),
        key_fn=lambda instance: instance.key,
        factory=lambda instance: [
            IncusInstanceButton(coordinator, entry, instance, description)
            for description in INSTANCE_BUTTONS
        ],
    )
    discoverer()
    entry.async_on_unload(coordinator.async_add_listener(discoverer))

    async_add_entities([IncusRefreshButton(coordinator, entry)])
