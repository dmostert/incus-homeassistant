"""Shared fixtures for the Incus integration tests."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.incus.const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PORT,
    CONF_VERIFY_SSL,
    CONNECTION_TLS,
    DOMAIN,
)
from custom_components.incus.incus_client import IncusConnectionParams

# ---------------------------------------------------------------------------
# Canned Incus API payloads
# ---------------------------------------------------------------------------

SERVER_RAW: dict[str, Any] = {
    "api_version": "1.0",
    "auth": "trusted",
    "api_extensions": ["instance_metrics"],
    "environment": {
        "server_name": "incus-test",
        "server_version": "6.0.1",
        "driver": "lxc",
        "storage": "zfs",
        "kernel": "Linux",
        "kernel_version": "6.8.0-31-generic",
        "os_name": "Ubuntu",
        "os_version": "24.04",
        "server_clustered": False,
        "certificate_fingerprint": "deadbeef",
    },
}

INSTANCE_RAW: dict[str, Any] = {
    "name": "web",
    "project": "default",
    "type": "container",
    "status": "Running",
    "status_code": 103,
    "location": "none",
    "description": "web server",
    "created_at": "2024-01-01T00:00:00+00:00",
    "last_used_at": "2024-01-02T00:00:00+00:00",
    "state": {
        "status": "Running",
        "status_code": 103,
        "processes": 12,
        "pid": 4321,
        "started_at": "2024-01-01T00:00:00+00:00",
        "cpu": {"usage": 1_000_000_000, "allocated_time": 1_000_000_000},
        "memory": {
            "usage": 25_000_000,
            "usage_peak": 30_000_000,
            "total": 100_000_000,
            "swap_usage": 1_000_000,
        },
        "disk": {
            "root": {
                "usage": 5_000_000,
                "total": 10_000_000,
                "counters": {"bytes_read": 1000, "bytes_written": 2000},
            }
        },
        "network": {
            "eth0": {
                "counters": {"bytes_received": 1000, "bytes_sent": 2000},
                "addresses": [
                    {"family": "inet", "scope": "global", "address": "10.0.0.5"}
                ],
            }
        },
    },
}

POOL_RAW: dict[str, Any] = {"name": "local", "driver": "zfs", "status": "Created"}

POOL_RESOURCES_RAW: dict[str, Any] = {
    "space": {"used": 30_000_000_000, "total": 100_000_000_000},
    "inodes": {"used": 100, "total": 1000},
}

VOLUME_RAW: dict[str, Any] = {
    "name": "data",
    "type": "custom",
    "content_type": "filesystem",
    "project": "default",
    "used_by": ["/1.0/instances/web"],
    "state": {"usage": {"used": 25_000_000, "total": 100_000_000}},
}


def instance(name: str, **state_overrides: Any) -> dict[str, Any]:
    """Return a copy of the sample instance with a different name/state."""
    raw = deepcopy(INSTANCE_RAW)
    raw["name"] = name
    raw["state"].update(state_overrides)
    return raw


class FakeIncusClient:
    """A recording stand-in for :class:`IncusClient` serving canned data."""

    def __init__(self, params: IncusConnectionParams) -> None:
        """Initialise the fake with the sample data."""
        self.params = params
        self.closed = False
        self.calls: list[str] = []
        self.actions: list[tuple[str, str]] = []

        self.server_raw = deepcopy(SERVER_RAW)
        self.instances_raw = [deepcopy(INSTANCE_RAW)]
        self.pools_raw = [deepcopy(POOL_RAW)]
        self.pool_resources_raw = {"local": deepcopy(POOL_RESOURCES_RAW)}
        self.pool_volumes_raw = {"local": [deepcopy(VOLUME_RAW)]}

        self.connect_error: Exception | None = None
        self.server_error: Exception | None = None
        self.instances_error: Exception | None = None
        self.action_error: Exception | None = None

    async def async_connect(self) -> None:
        self.calls.append("async_connect")
        if self.connect_error is not None:
            raise self.connect_error

    async def close(self) -> None:
        self.calls.append("close")
        self.closed = True

    async def async_get_server(self) -> dict[str, Any]:
        self.calls.append("async_get_server")
        if self.server_error is not None:
            raise self.server_error
        return self.server_raw

    async def async_get_instances(
        self, *, all_projects: bool = False, recursion: int = 2
    ) -> list[dict[str, Any]]:
        self.calls.append("async_get_instances")
        if self.instances_error is not None:
            raise self.instances_error
        return self.instances_raw

    async def async_get_instance_state(
        self, name: str, *, project: str | None = None
    ) -> dict[str, Any]:
        self.calls.append("async_get_instance_state")
        for raw in self.instances_raw:
            if raw["name"] == name:
                return raw.get("state", {})
        return {}

    async def async_get_storage_pools(self) -> list[dict[str, Any]]:
        self.calls.append("async_get_storage_pools")
        return self.pools_raw

    async def async_get_storage_pool_resources(self, pool: str) -> dict[str, Any]:
        self.calls.append("async_get_storage_pool_resources")
        return self.pool_resources_raw.get(pool, {})

    async def async_get_storage_pool_volumes(
        self, pool: str, *, all_projects: bool = False, recursion: int = 2
    ) -> list[dict[str, Any]]:
        self.calls.append("async_get_storage_pool_volumes")
        return self.pool_volumes_raw.get(pool, [])

    async def async_get_storage_pool_volume_state(
        self, pool: str, volume_type: str, name: str, *, project: str | None = None
    ) -> dict[str, Any]:
        self.calls.append("async_get_storage_pool_volume_state")
        return {}

    async def async_set_instance_state(
        self,
        name: str,
        action: str,
        *,
        project: str | None = None,
        timeout: int = 30,
        force: bool = False,
        stateful: bool = False,
    ) -> dict[str, Any]:
        self.calls.append("async_set_instance_state")
        if self.action_error is not None:
            raise self.action_error
        self.actions.append((name, action))
        return {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the custom integration loadable in every test."""
    yield


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeIncusClient:
    """Patch IncusClient with a recording fake and return it."""
    client = FakeIncusClient(
        IncusConnectionParams(
            connection_type=CONNECTION_TLS, host="incus.local", port=8443
        )
    )
    monkeypatch.setattr("custom_components.incus.IncusClient", lambda params: client)
    monkeypatch.setattr(
        "custom_components.incus.config_flow.IncusClient", lambda params: client
    )
    return client


@pytest.fixture
def make_entry() -> Callable[..., MockConfigEntry]:
    """Return a factory for Incus config entries."""

    def _make(**kwargs: Any) -> MockConfigEntry:
        data = {
            CONF_CONNECTION_TYPE: CONNECTION_TLS,
            CONF_HOST: "incus.local",
            CONF_PORT: 8443,
            CONF_VERIFY_SSL: True,
            **kwargs.pop("data", {}),
        }
        return MockConfigEntry(
            domain=DOMAIN,
            title="Incus (incus-test)",
            unique_id="deadbeef",
            data=data,
            **kwargs,
        )

    return _make


@pytest.fixture
def config_entry(make_entry: Callable[..., MockConfigEntry]) -> MockConfigEntry:
    """Return a TLS config entry."""
    return make_entry()


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant,
    fake_client: FakeIncusClient,
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Add the config entry and set it up."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
