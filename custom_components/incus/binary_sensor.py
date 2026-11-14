"""Binary sensor platform for the Incus integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import STATUS_ERROR
from .coordinator import IncusCoordinator, InstanceData
from .entity import EntityDiscoverer, IncusInstanceEntity


@dataclass(frozen=True, kw_only=True)
class IncusBinarySensorDescription(BinarySensorEntityDescription):
    """Description of an instance binary sensor."""

    value_fn: Callable[[InstanceData], bool]


INSTANCE_BINARY_SENSORS: tuple[IncusBinarySensorDescription, ...] = (
    IncusBinarySensorDescription(
        key="running",
        name="Running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda instance: instance.is_active,
    ),
    IncusBinarySensorDescription(
        key="problem",
        name="Problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.status == STATUS_ERROR,
    ),
)


class IncusInstanceBinarySensor(IncusInstanceEntity, BinarySensorEntity):
    """A binary sensor for a single Incus instance."""

    entity_description: IncusBinarySensorDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        instance: InstanceData,
        description: IncusBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, entry, instance)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{instance.key}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state."""
        instance = self.instance
        if instance is None:
            return None
        return self.entity_description.value_fn(instance)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Incus binary sensors."""
    coordinator: IncusCoordinator = entry.runtime_data

    discoverer = EntityDiscoverer(
        hass,
        coordinator,
        async_add_entities,
        items_fn=lambda data: data.instances.values(),
        key_fn=lambda instance: instance.key,
        factory=lambda instance: [
            IncusInstanceBinarySensor(coordinator, entry, instance, description)
            for description in INSTANCE_BINARY_SENSORS
        ],
    )
    discoverer()
    entry.async_on_unload(coordinator.async_add_listener(discoverer))
