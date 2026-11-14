"""Data update coordinator for the Incus integration."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_STATUSES,
    CONF_ALL_PROJECTS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .incus_client import (
    IncusAPIError,
    IncusAuthError,
    IncusClient,
    IncusConnectionError,
    IncusError,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InstanceData:
    """Normalised information about a single Incus instance."""

    key: str
    name: str
    project: str
    instance_type: str
    status: str
    status_code: int
    location: str
    description: str
    created_at: str | None
    last_used_at: str | None
    cpu_usage_ns: int
    cpu_allocated_ns: int
    cpu_percent: float | None
    memory_usage: int
    memory_peak: int
    memory_total: int
    memory_swap_usage: int
    memory_percent: float | None
    processes: int
    pid: int
    disk_usage: int
    disk_total: int
    disk_read_bytes: int
    disk_written_bytes: int
    network_rx_bytes: int
    network_tx_bytes: int
    ip_address: str | None
    started_at: str | None
    uptime: int | None

    @property
    def is_active(self) -> bool:
        """Return True when the instance is running (or frozen)."""
        return self.status in ACTIVE_STATUSES


@dataclass(slots=True)
class VolumeData:
    """Normalised information about a single storage volume."""

    key: str
    name: str
    pool: str
    volume_type: str
    content_type: str
    project: str
    used_by: list[str]
    used: int
    total: int
    percent: float | None


@dataclass(slots=True)
class PoolData:
    """Normalised information about a storage pool."""

    name: str
    driver: str
    status: str
    used: int
    total: int
    free: int
    percent: float | None
    inodes_used: int
    inodes_total: int
    volume_count: int


@dataclass(slots=True)
class ServerData:
    """Normalised information about the Incus server."""

    name: str
    version: str
    api_version: str
    driver: str
    storage_driver: str
    kernel: str
    kernel_version: str
    os_name: str
    os_version: str
    clustered: bool
    auth: str
    certificate_fingerprint: str | None
    api_extensions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IncusData:
    """All data gathered on a single poll."""

    server: ServerData
    instances: dict[str, InstanceData]
    volumes: dict[str, VolumeData]
    pools: dict[str, PoolData]


def _int(value: Any) -> int:
    """Best effort conversion to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _percent(used: int, total: int) -> float | None:
    if not total:
        return None
    return round(used / total * 100, 2)


def _parse_instance(raw: dict[str, Any]) -> InstanceData:
    state: dict[str, Any] = raw.get("state") or {}
    cpu: dict[str, Any] = state.get("cpu") or {}
    memory: dict[str, Any] = state.get("memory") or {}
    disk: dict[str, Any] = state.get("disk") or {}
    network: dict[str, Any] = state.get("network") or {}

    name = raw.get("name", "")
    project = raw.get("project") or "default"

    disk_usage = 0
    disk_total = 0
    disk_read = 0
    disk_written = 0
    for entry in disk.values():
        disk_usage += _int(entry.get("usage"))
        disk_total += _int(entry.get("total"))
        counters = entry.get("counters") or {}
        disk_read += _int(counters.get("bytes_read"))
        disk_written += _int(counters.get("bytes_written"))

    network_rx = 0
    network_tx = 0
    ip_address: str | None = None
    for interface in network.values():
        counters = interface.get("counters") or {}
        network_rx += _int(counters.get("bytes_received"))
        network_tx += _int(counters.get("bytes_sent"))
        if ip_address is None:
            for address in interface.get("addresses") or []:
                if address.get("family") == "inet" and address.get("scope") == "global":
                    ip_address = address.get("address")
                    break

    memory_usage = _int(memory.get("usage"))
    memory_total = _int(memory.get("total"))

    status = state.get("status") or raw.get("status") or "Unknown"
    started_at = state.get("started_at")
    uptime: int | None = None
    if status in ACTIVE_STATUSES and started_at:
        started = dt_util.parse_datetime(started_at)
        if started is not None:
            uptime = max(0, int((dt_util.utcnow() - started).total_seconds()))

    return InstanceData(
        key=f"{project}/{name}",
        name=name,
        project=project,
        instance_type=raw.get("type", "container"),
        status=status,
        status_code=_int(raw.get("status_code") or state.get("status_code")),
        location=raw.get("location") or "",
        description=raw.get("description") or "",
        created_at=raw.get("created_at"),
        last_used_at=raw.get("last_used_at"),
        cpu_usage_ns=_int(cpu.get("usage")),
        cpu_allocated_ns=_int(cpu.get("allocated_time")),
        cpu_percent=None,
        memory_usage=memory_usage,
        memory_peak=_int(memory.get("usage_peak")),
        memory_total=memory_total,
        memory_swap_usage=_int(memory.get("swap_usage")),
        memory_percent=_percent(memory_usage, memory_total),
        processes=_int(state.get("processes")),
        pid=_int(state.get("pid")),
        disk_usage=disk_usage,
        disk_total=disk_total,
        disk_read_bytes=disk_read,
        disk_written_bytes=disk_written,
        network_rx_bytes=network_rx,
        network_tx_bytes=network_tx,
        ip_address=ip_address,
        started_at=started_at,
        uptime=uptime,
    )


def _parse_volume(raw: dict[str, Any], pool: str) -> VolumeData:
    state: dict[str, Any] = raw.get("state") or {}
    usage: dict[str, Any] = state.get("usage") or {}
    used = _int(usage.get("used"))
    total = _int(usage.get("total"))
    name = raw.get("name", "")
    return VolumeData(
        key=f"{pool}/{name}",
        name=name,
        pool=pool,
        volume_type=raw.get("type", "custom"),
        content_type=raw.get("content_type") or "filesystem",
        project=raw.get("project") or "default",
        used_by=list(raw.get("used_by") or []),
        used=used,
        total=total,
        percent=_percent(used, total),
    )


def _parse_pool(
    raw: dict[str, Any], resources: dict[str, Any], volume_count: int
) -> PoolData:
    space: dict[str, Any] = resources.get("space") or {}
    inodes: dict[str, Any] = resources.get("inodes") or {}
    used = _int(space.get("used"))
    total = _int(space.get("total"))
    return PoolData(
        name=raw.get("name", ""),
        driver=raw.get("driver", ""),
        status=raw.get("status", ""),
        used=used,
        total=total,
        free=max(0, total - used),
        percent=_percent(used, total),
        inodes_used=_int(inodes.get("used")),
        inodes_total=_int(inodes.get("total")),
        volume_count=volume_count,
    )


def _parse_server(raw: dict[str, Any]) -> ServerData:
    environment: dict[str, Any] = raw.get("environment") or {}
    return ServerData(
        name=environment.get("server_name") or "Incus",
        version=environment.get("server_version") or "",
        api_version=raw.get("api_version") or "",
        driver=environment.get("driver") or "",
        storage_driver=environment.get("storage") or "",
        kernel=environment.get("kernel") or "",
        kernel_version=environment.get("kernel_version") or "",
        os_name=environment.get("os_name") or "",
        os_version=environment.get("os_version") or "",
        clustered=bool(environment.get("server_clustered")),
        auth=raw.get("auth") or "trusted",
        certificate_fingerprint=environment.get("certificate_fingerprint"),
        api_extensions=list(raw.get("api_extensions") or []),
    )


class IncusCoordinator(DataUpdateCoordinator[IncusData]):
    """Polls an Incus server and normalises the results."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: IncusClient,
    ) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        self.client = client
        self.all_projects = entry.options.get(CONF_ALL_PROJECTS, False)
        # Keeps the previous CPU sample so we can turn the cumulative counter
        # into a percentage: {instance_key: (usage_ns, monotonic_ts)}.
        self._cpu_samples: dict[str, tuple[int, float]] = {}

        update_interval = timedelta(
            seconds=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )

        self.configuration_url: str | None = None
        if client.params.connection_type == "tls" and client.params.host:
            scheme = "https" if client.params.port != 80 else "http"
            self.configuration_url = (
                f"{scheme}://{client.params.host}:{client.params.port}"
            )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> IncusData:
        """Fetch the latest data from the Incus server."""
        try:
            server_raw = await self.client.async_get_server()
            instances_raw = await self.client.async_get_instances(
                all_projects=self.all_projects
            )
            pools_raw = await self.client.async_get_storage_pools()
        except IncusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IncusConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except IncusAPIError as err:
            raise UpdateFailed(f"Incus API error: {err}") from err

        server = _parse_server(server_raw)

        # Instances ----------------------------------------------------
        now = time.monotonic()
        instances: dict[str, InstanceData] = {}
        for raw in instances_raw:
            instance = _parse_instance(raw)
            if raw.get("state") is None:
                # Fall back to an explicit state call when the server did not
                # inline the state with recursion=2.
                try:
                    state = await self.client.async_get_instance_state(
                        instance.name, project=instance.project
                    )
                except IncusError:
                    state = {}
                raw = {**raw, "state": state}
                instance = _parse_instance(raw)
            self._apply_cpu_percent(instance, now)
            instances[instance.key] = instance

        # Drop stale CPU samples so the dict cannot grow forever.
        for key in set(self._cpu_samples) - set(instances):
            self._cpu_samples.pop(key, None)

        # Storage ------------------------------------------------------
        pools: dict[str, PoolData] = {}
        volumes: dict[str, VolumeData] = {}
        pool_results = await asyncio.gather(
            *(self._async_collect_pool(raw) for raw in pools_raw),
            return_exceptions=True,
        )
        for result in pool_results:
            if isinstance(result, Exception):
                _LOGGER.debug("Error collecting storage pool data: %s", result)
                continue
            pool, pool_volumes = result
            pools[pool.name] = pool
            for volume in pool_volumes:
                volumes[volume.key] = volume

        return IncusData(
            server=server,
            instances=instances,
            volumes=volumes,
            pools=pools,
        )

    async def _async_collect_pool(
        self, raw: dict[str, Any]
    ) -> tuple[PoolData, list[VolumeData]]:
        """Collect resources and volumes for a single storage pool."""
        pool_name = raw.get("name", "")
        resources: dict[str, Any] = {}
        volumes_raw: list[dict[str, Any]] = []

        try:
            resources = await self.client.async_get_storage_pool_resources(pool_name)
        except IncusError as err:
            _LOGGER.debug("Unable to read resources for pool %s: %s", pool_name, err)

        try:
            volumes_raw = await self.client.async_get_storage_pool_volumes(
                pool_name, all_projects=self.all_projects
            )
        except IncusError as err:
            _LOGGER.debug("Unable to read volumes for pool %s: %s", pool_name, err)

        volumes: list[VolumeData] = []
        for volume_raw in volumes_raw:
            volume = _parse_volume(volume_raw, pool_name)
            if volume_raw.get("state") is None and volume.volume_type == "custom":
                try:
                    state = await self.client.async_get_storage_pool_volume_state(
                        pool_name,
                        volume.volume_type,
                        volume.name,
                        project=volume.project,
                    )
                    volume = _parse_volume({**volume_raw, "state": state}, pool_name)
                except IncusError:
                    pass
            volumes.append(volume)

        pool = _parse_pool(raw, resources, len(volumes))
        return pool, volumes

    def _apply_cpu_percent(self, instance: InstanceData, now: float) -> None:
        """Turn the cumulative CPU counter into a percentage."""
        previous = self._cpu_samples.get(instance.key)
        self._cpu_samples[instance.key] = (instance.cpu_usage_ns, now)

        if previous is None or not instance.is_active:
            return

        prev_usage, prev_ts = previous
        elapsed = now - prev_ts
        delta = instance.cpu_usage_ns - prev_usage
        if elapsed <= 0 or delta < 0:
            return

        # ``allocated_time`` is the CPU time available per second (ns). When the
        # server does not expose it, fall back to a single core.
        capacity_ns_per_second = instance.cpu_allocated_ns or 1_000_000_000
        instance.cpu_percent = round(
            delta / (elapsed * capacity_ns_per_second) * 100, 2
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    async def async_instance_action(
        self,
        name: str,
        action: str,
        *,
        project: str | None = None,
        force: bool = False,
        timeout: int = 30,
        stateful: bool = False,
    ) -> None:
        """Execute a state change against an instance and refresh."""
        await self.client.async_set_instance_state(
            name,
            action,
            project=project,
            force=force,
            timeout=timeout,
            stateful=stateful,
        )
        await self.async_request_refresh()

    def find_instance(
        self, name: str, project: str | None = None
    ) -> InstanceData | None:
        """Look up an instance by name (optionally scoped to a project)."""
        if not self.data:
            return None
        if project is not None:
            return self.data.instances.get(f"{project}/{name}")
        for instance in self.data.instances.values():
            if instance.name == name:
                return instance
        return None
