"""Tests for the Incus coordinator, parsing and connection parameters."""

from __future__ import annotations

from copy import deepcopy

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.incus import build_connection_params
from custom_components.incus.const import (
    CONF_ALL_PROJECTS,
    CONF_CONNECTION_TYPE,
    CONF_SOCKET_PATH,
    CONNECTION_TLS,
    CONNECTION_UNIX,
    DOMAIN,
)
from custom_components.incus.incus_client import (
    IncusAuthError,
    IncusConnectionError,
)

from .conftest import INSTANCE_RAW, FakeIncusClient, instance


def test_build_connection_params_tls(config_entry: MockConfigEntry) -> None:
    """TLS entries are converted to TLS connection parameters."""
    params = build_connection_params(config_entry)
    assert params.connection_type == CONNECTION_TLS
    assert params.host == "incus.local"
    assert params.port == 8443
    assert params.verify_ssl is True


def test_build_connection_params_unix() -> None:
    """Unix entries are converted to Unix connection parameters."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_UNIX,
            CONF_SOCKET_PATH: "/tmp/incus.sock",
        },
    )
    params = build_connection_params(entry)
    assert params.connection_type == CONNECTION_UNIX
    assert params.socket_path == "/tmp/incus.sock"


async def test_coordinator_parses_data(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """The coordinator normalises server, instance and storage data."""
    data = setup_entry.runtime_data.data

    assert data.server.name == "incus-test"
    assert data.server.version == "6.0.1"
    assert data.server.api_version == "1.0"
    assert data.server.storage_driver == "zfs"
    assert data.server.clustered is False

    assert set(data.instances) == {"default/web"}
    web = data.instances["default/web"]
    assert web.name == "web"
    assert web.status == "Running"
    assert web.is_active is True
    assert web.memory_usage == 25_000_000
    assert web.memory_total == 100_000_000
    assert web.memory_percent == 25.0
    assert web.processes == 12
    assert web.disk_usage == 5_000_000
    assert web.disk_read_bytes == 1000
    assert web.disk_written_bytes == 2000
    assert web.network_rx_bytes == 1000
    assert web.network_tx_bytes == 2000
    assert web.ip_address == "10.0.0.5"
    assert web.uptime is not None

    assert set(data.pools) == {"local"}
    pool = data.pools["local"]
    assert pool.used == 30_000_000_000
    assert pool.total == 100_000_000_000
    assert pool.free == 70_000_000_000
    assert pool.percent == 30.0
    assert pool.inodes_used == 100
    assert pool.volume_count == 1

    assert set(data.volumes) == {"local/data"}
    volume = data.volumes["local/data"]
    assert volume.used == 25_000_000
    assert volume.total == 100_000_000
    assert volume.percent == 25.0
    assert volume.used_by == ["/1.0/instances/web"]


async def test_cpu_percent(
    hass: HomeAssistant,
    fake_client: FakeIncusClient,
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cumulative CPU counter is turned into a percentage."""
    clock = {"t": 100.0}
    monkeypatch.setattr(
        "custom_components.incus.coordinator.time.monotonic", lambda: clock["t"]
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.data.instances["default/web"].cpu_percent is None

    updated = deepcopy(INSTANCE_RAW)
    updated["state"]["cpu"]["usage"] = 3_000_000_000
    fake_client.instances_raw = [updated]
    clock["t"] = 102.0
    await coordinator.async_refresh()

    assert coordinator.data.instances["default/web"].cpu_percent == 100.0


async def test_find_instance(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Instances can be looked up by name and project."""
    coordinator = setup_entry.runtime_data
    assert coordinator.find_instance("web") is not None
    assert coordinator.find_instance("web", "default") is not None
    assert coordinator.find_instance("web", "other") is None
    assert coordinator.find_instance("missing") is None


async def test_dynamic_discovery(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """New instances appear and removed instances disappear after a refresh."""
    coordinator = setup_entry.runtime_data
    assert hass.states.get("sensor.web_memory_usage") is not None

    fake_client.instances_raw = [deepcopy(INSTANCE_RAW), instance("db")]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.db_memory_usage") is not None

    fake_client.instances_raw = [deepcopy(INSTANCE_RAW)]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get("sensor.db_memory_usage") is None
    assert hass.states.get("sensor.db_memory_usage") is None
    # The disabled-by-default disk sensors are cleaned up as well.
    assert registry.async_get("sensor.db_disk_read") is None
    assert hass.states.get("sensor.web_memory_usage") is not None


async def test_all_projects_option(
    hass: HomeAssistant, fake_client: FakeIncusClient, make_entry
) -> None:
    """The all-projects option is forwarded to the client."""
    entry = make_entry(options={CONF_ALL_PROJECTS: True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.all_projects is True


async def test_setup_retries_on_connection_error(
    hass: HomeAssistant, fake_client: FakeIncusClient, config_entry: MockConfigEntry
) -> None:
    """A connection error makes setup retry."""
    fake_client.connect_error = IncusConnectionError("boom")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_on_auth_error(
    hass: HomeAssistant, fake_client: FakeIncusClient, config_entry: MockConfigEntry
) -> None:
    """An authentication error makes setup fail."""
    fake_client.server_error = IncusAuthError("untrusted")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
