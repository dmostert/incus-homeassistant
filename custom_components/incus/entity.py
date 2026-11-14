"""Base entity classes for the Incus integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import (
    IncusCoordinator,
    IncusData,
    InstanceData,
    PoolData,
    VolumeData,
)


class IncusBaseEntity(CoordinatorEntity[IncusCoordinator]):
    """Common functionality shared by all Incus entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IncusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entry = entry

    @property
    def hub_device_identifier(self) -> tuple[str, str]:
        """Return the identifier of the hub (server) device."""
        return (DOMAIN, self.entry.entry_id)

    @property
    def hub_device_info(self) -> DeviceInfo:
        """Return the device info of the hub (server) device."""
        server = self.coordinator.data.server if self.coordinator.data else None
        return DeviceInfo(
            identifiers={self.hub_device_identifier},
            name=f"Incus ({server.name})" if server else "Incus",
            manufacturer=MANUFACTURER,
            model="Incus Server",
            sw_version=server.version if server else None,
            configuration_url=self.coordinator.configuration_url,
        )


class IncusInstanceEntity(IncusBaseEntity):
    """Base class for entities that belong to a single instance."""

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        instance: InstanceData,
    ) -> None:
        """Initialise the entity from an instance snapshot."""
        super().__init__(coordinator, entry)
        self._key = instance.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_instance_{instance.key}")},
            name=instance.name,
            via_device_id=self.coordinator.hub_device_id,
            manufacturer=MANUFACTURER,
            model=f"Incus {instance.instance_type}",
        )

    @property
    def instance(self) -> InstanceData | None:
        """Return the current data for this instance."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.instances.get(self._key)

    @property
    def available(self) -> bool:
        """Return whether the instance still exists and the poll succeeded."""
        return super().available and self.instance is not None


class IncusVolumeEntity(IncusBaseEntity):
    """Base class for entities that belong to a single storage volume."""

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        volume: VolumeData,
    ) -> None:
        """Initialise the entity from a volume snapshot."""
        super().__init__(coordinator, entry)
        self._key = volume.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_volume_{volume.key}")},
            name=f"{volume.pool}/{volume.name}",
            via_device_id=self.coordinator.hub_device_id,
            manufacturer=MANUFACTURER,
            model=f"Incus {volume.volume_type} volume",
        )

    @property
    def volume(self) -> VolumeData | None:
        """Return the current data for this volume."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.volumes.get(self._key)

    @property
    def available(self) -> bool:
        """Return whether the volume still exists and the poll succeeded."""
        return super().available and self.volume is not None


class IncusPoolEntity(IncusBaseEntity):
    """Base class for entities that belong to a storage pool."""

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        pool: PoolData,
    ) -> None:
        """Initialise the entity from a pool snapshot."""
        super().__init__(coordinator, entry)
        self._key = pool.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_pool_{pool.name}")},
            name=f"Storage pool {pool.name}",
            via_device_id=self.coordinator.hub_device_id,
            manufacturer=MANUFACTURER,
            model=f"Incus {pool.driver} pool",
        )

    @property
    def pool(self) -> PoolData | None:
        """Return the current data for this pool."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.pools.get(self._key)

    @property
    def available(self) -> bool:
        """Return whether the pool still exists and the poll succeeded."""
        return super().available and self.pool is not None


class EntityDiscoverer[T]:
    """Create entities for newly discovered items and drop removed ones.

    Home Assistant integrations must add entities from a callback that runs in
    the event loop. This helper is registered as a coordinator listener so that
    new instances/volumes/pools automatically appear after a refresh, and
    entities disappear again when their item is deleted on the Incus server.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: IncusCoordinator,
        async_add_entities: AddEntitiesCallback,
        items_fn: Callable[[IncusData], Iterable[T]],
        key_fn: Callable[[T], str],
        factory: Callable[[T], Iterable[Entity]],
    ) -> None:
        """Initialise the discoverer.

        ``factory`` may return one or more entities for a single item (for
        example one sensor per metric). All entities produced for the same item
        share the item key so they are added and removed together.
        """
        self._hass = hass
        self._coordinator = coordinator
        self._async_add_entities = async_add_entities
        self._items_fn = items_fn
        self._key_fn = key_fn
        self._factory = factory
        self._known: dict[str, list[Entity]] = {}

    def __call__(self) -> None:
        """Reconcile the current entities with the latest coordinator data."""
        data = self._coordinator.data
        if data is None:
            return

        items = list(self._items_fn(data))
        current = {self._key_fn(item) for item in items}

        registry = er.async_get(self._hass)
        for key in list(self._known):
            if key not in current:
                for entity in self._known.pop(key):
                    # Remove the entity through the registry: this drops both
                    # the registry entry and the state. Entities that are
                    # disabled by default never get a state but still own a
                    # registry entry, which must go too.
                    entity_id = entity.entity_id
                    if entity_id and registry.async_get(entity_id):
                        registry.async_remove(entity_id)

        new_entities: list[Entity] = []
        for item in items:
            key = self._key_fn(item)
            if key in self._known:
                continue
            entities = list(self._factory(item))
            self._known[key] = entities
            new_entities.extend(entities)

        if new_entities:
            self._async_add_entities(new_entities)
