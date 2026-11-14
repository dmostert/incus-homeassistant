"""Sensor platform for the Incus integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_INSTANCE_SENSORS,
    CONF_ENABLE_PERFORMANCE_SENSORS,
    CONF_ENABLE_POOL_SENSORS,
    CONF_ENABLE_VOLUME_SENSORS,
)
from .coordinator import (
    IncusCoordinator,
    IncusData,
    InstanceData,
    PoolData,
    VolumeData,
)
from .entity import (
    EntityDiscoverer,
    IncusBaseEntity,
    IncusInstanceEntity,
    IncusPoolEntity,
    IncusVolumeEntity,
)


@dataclass(frozen=True, kw_only=True)
class IncusInstanceSensorDescription(SensorEntityDescription):
    """Description of an instance sensor."""

    value_fn: Callable[[InstanceData], Any]
    performance: bool = False


@dataclass(frozen=True, kw_only=True)
class IncusVolumeSensorDescription(SensorEntityDescription):
    """Description of a volume sensor."""

    value_fn: Callable[[VolumeData], Any]


@dataclass(frozen=True, kw_only=True)
class IncusPoolSensorDescription(SensorEntityDescription):
    """Description of a storage pool sensor."""

    value_fn: Callable[[PoolData], Any]


@dataclass(frozen=True, kw_only=True)
class IncusServerSensorDescription(SensorEntityDescription):
    """Description of a server sensor."""

    value_fn: Callable[[IncusData], Any]


INSTANCE_SENSORS: tuple[IncusInstanceSensorDescription, ...] = (
    IncusInstanceSensorDescription(
        key="status",
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "Running",
            "Stopped",
            "Frozen",
            "Starting",
            "Stopping",
            "Migrating",
            "Creating",
            "Freezing",
            "Thawed",
            "Error",
            "Ready",
            "Pending",
            "Unknown",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.status,
    ),
    IncusInstanceSensorDescription(
        key="cpu_usage",
        name="CPU usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        performance=True,
        value_fn=lambda instance: instance.cpu_percent,
    ),
    IncusInstanceSensorDescription(
        key="memory_usage",
        name="Memory usage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        performance=True,
        value_fn=lambda instance: instance.memory_usage,
    ),
    IncusInstanceSensorDescription(
        key="memory_usage_percent",
        name="Memory usage percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        performance=True,
        value_fn=lambda instance: instance.memory_percent,
    ),
    IncusInstanceSensorDescription(
        key="memory_total",
        name="Memory total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.memory_total or None,
    ),
    IncusInstanceSensorDescription(
        key="memory_peak",
        name="Memory peak",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.memory_peak or None,
    ),
    IncusInstanceSensorDescription(
        key="swap_usage",
        name="Swap usage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        performance=True,
        value_fn=lambda instance: instance.memory_swap_usage,
    ),
    IncusInstanceSensorDescription(
        key="processes",
        name="Processes",
        state_class=SensorStateClass.MEASUREMENT,
        performance=True,
        value_fn=lambda instance: instance.processes,
    ),
    IncusInstanceSensorDescription(
        key="disk_usage",
        name="Disk usage",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        performance=True,
        value_fn=lambda instance: instance.disk_usage,
    ),
    IncusInstanceSensorDescription(
        key="disk_total",
        name="Disk total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.disk_total or None,
    ),
    IncusInstanceSensorDescription(
        key="disk_read",
        name="Disk read",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        performance=True,
        value_fn=lambda instance: instance.disk_read_bytes,
    ),
    IncusInstanceSensorDescription(
        key="disk_written",
        name="Disk written",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        performance=True,
        value_fn=lambda instance: instance.disk_written_bytes,
    ),
    IncusInstanceSensorDescription(
        key="network_received",
        name="Network received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        performance=True,
        value_fn=lambda instance: instance.network_rx_bytes,
    ),
    IncusInstanceSensorDescription(
        key="network_sent",
        name="Network sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        performance=True,
        value_fn=lambda instance: instance.network_tx_bytes,
    ),
    IncusInstanceSensorDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.uptime,
    ),
    IncusInstanceSensorDescription(
        key="ip_address",
        name="IP address",
        icon="mdi:ip",
        value_fn=lambda instance: instance.ip_address,
    ),
    IncusInstanceSensorDescription(
        key="instance_type",
        name="Instance type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda instance: instance.instance_type,
    ),
)

VOLUME_SENSORS: tuple[IncusVolumeSensorDescription, ...] = (
    IncusVolumeSensorDescription(
        key="used",
        name="Used space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda volume: volume.used,
    ),
    IncusVolumeSensorDescription(
        key="total",
        name="Total space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda volume: volume.total or None,
    ),
    IncusVolumeSensorDescription(
        key="percent",
        name="Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda volume: volume.percent,
    ),
    IncusVolumeSensorDescription(
        key="used_by",
        name="Used by",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda volume: len(volume.used_by),
    ),
)

POOL_SENSORS: tuple[IncusPoolSensorDescription, ...] = (
    IncusPoolSensorDescription(
        key="used",
        name="Used space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda pool: pool.used,
    ),
    IncusPoolSensorDescription(
        key="free",
        name="Free space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda pool: pool.free,
    ),
    IncusPoolSensorDescription(
        key="total",
        name="Total space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pool: pool.total or None,
    ),
    IncusPoolSensorDescription(
        key="percent",
        name="Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda pool: pool.percent,
    ),
    IncusPoolSensorDescription(
        key="inodes_used",
        name="Inodes used",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pool: pool.inodes_used,
    ),
    IncusPoolSensorDescription(
        key="inodes_total",
        name="Inodes total",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pool: pool.inodes_total or None,
    ),
    IncusPoolSensorDescription(
        key="volumes",
        name="Volumes",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda pool: pool.volume_count,
    ),
)

SERVER_SENSORS: tuple[IncusServerSensorDescription, ...] = (
    IncusServerSensorDescription(
        key="instances_running",
        name="Instances running",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(
            1 for instance in data.instances.values() if instance.is_active
        ),
    ),
    IncusServerSensorDescription(
        key="instances_total",
        name="Instances total",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.instances),
    ),
    IncusServerSensorDescription(
        key="volumes_total",
        name="Volumes total",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.volumes),
    ),
    IncusServerSensorDescription(
        key="pools_total",
        name="Storage pools",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.pools),
    ),
    IncusServerSensorDescription(
        key="server_version",
        name="Server version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.server.version or None,
    ),
    IncusServerSensorDescription(
        key="api_version",
        name="API version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.server.api_version or None,
    ),
    IncusServerSensorDescription(
        key="kernel_version",
        name="Kernel version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.server.kernel_version or None,
    ),
    IncusServerSensorDescription(
        key="storage_driver",
        name="Storage driver",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.server.storage_driver or None,
    ),
)


class IncusInstanceSensor(IncusInstanceEntity, SensorEntity):
    """A sensor that reports a metric of an Incus instance."""

    entity_description: IncusInstanceSensorDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        instance: InstanceData,
        description: IncusInstanceSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, instance)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{instance.key}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        instance = self.instance
        if instance is None:
            return None
        return self.entity_description.value_fn(instance)


class IncusVolumeSensor(IncusVolumeEntity, SensorEntity):
    """A sensor that reports a metric of an Incus storage volume."""

    entity_description: IncusVolumeSensorDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        volume: VolumeData,
        description: IncusVolumeSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, volume)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{volume.key}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        volume = self.volume
        if volume is None:
            return None
        return self.entity_description.value_fn(volume)


class IncusPoolSensor(IncusPoolEntity, SensorEntity):
    """A sensor that reports a metric of an Incus storage pool."""

    entity_description: IncusPoolSensorDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        pool: PoolData,
        description: IncusPoolSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, pool)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{pool.name}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        pool = self.pool
        if pool is None:
            return None
        return self.entity_description.value_fn(pool)


class IncusServerSensor(IncusBaseEntity, SensorEntity):
    """A sensor that reports a metric of the Incus server."""

    entity_description: IncusServerSensorDescription

    def __init__(
        self,
        coordinator: IncusCoordinator,
        entry: ConfigEntry,
        description: IncusServerSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_device_info = self.hub_device_info
        self._attr_unique_id = f"{entry.entry_id}_server_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Incus sensors."""
    coordinator: IncusCoordinator = entry.runtime_data

    if entry.options.get(CONF_ENABLE_INSTANCE_SENSORS, True):
        enabled = tuple(
            description
            for description in INSTANCE_SENSORS
            if not description.performance
            or entry.options.get(CONF_ENABLE_PERFORMANCE_SENSORS, True)
        )
        instance_discoverer = EntityDiscoverer(
            hass,
            coordinator,
            async_add_entities,
            items_fn=lambda data: data.instances.values(),
            key_fn=lambda instance: instance.key,
            factory=lambda instance: [
                IncusInstanceSensor(coordinator, entry, instance, description)
                for description in enabled
            ],
        )
        instance_discoverer()
        entry.async_on_unload(coordinator.async_add_listener(instance_discoverer))

    if entry.options.get(CONF_ENABLE_VOLUME_SENSORS, True):
        volume_discoverer = EntityDiscoverer(
            hass,
            coordinator,
            async_add_entities,
            items_fn=lambda data: data.volumes.values(),
            key_fn=lambda volume: volume.key,
            factory=lambda volume: [
                IncusVolumeSensor(coordinator, entry, volume, description)
                for description in VOLUME_SENSORS
            ],
        )
        volume_discoverer()
        entry.async_on_unload(coordinator.async_add_listener(volume_discoverer))

    if entry.options.get(CONF_ENABLE_POOL_SENSORS, True):
        pool_discoverer = EntityDiscoverer(
            hass,
            coordinator,
            async_add_entities,
            items_fn=lambda data: data.pools.values(),
            key_fn=lambda pool: pool.name,
            factory=lambda pool: [
                IncusPoolSensor(coordinator, entry, pool, description)
                for description in POOL_SENSORS
            ],
        )
        pool_discoverer()
        entry.async_on_unload(coordinator.async_add_listener(pool_discoverer))

    # Server (hub) sensors are always created, once.
    async_add_entities(
        [
            IncusServerSensor(coordinator, entry, description)
            for description in SERVER_SENSORS
        ]
    )
