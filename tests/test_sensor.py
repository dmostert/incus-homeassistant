"""Tests for the Incus sensor, binary sensor, switch and button entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.incus.const import (
    CONF_ENABLE_PERFORMANCE_SENSORS,
    CONF_ENABLE_VOLUME_SENSORS,
)

from .conftest import FakeIncusClient


async def test_instance_entities(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Instance sensors, binary sensors, switch and buttons are created."""
    assert hass.states.get("sensor.web_status").state == "Running"
    assert hass.states.get("sensor.web_memory_usage").state == "25000000"
    assert hass.states.get("sensor.web_memory_usage_percent").state == "25.0"
    assert hass.states.get("sensor.web_memory_total").state == "100000000"
    assert hass.states.get("sensor.web_processes").state == "12"
    assert hass.states.get("sensor.web_disk_usage").state == "5000000"
    assert hass.states.get("sensor.web_network_received").state == "1000"
    assert hass.states.get("sensor.web_network_sent").state == "2000"
    assert hass.states.get("sensor.web_ip_address").state == "10.0.0.5"
    assert hass.states.get("sensor.web_instance_type").state == "container"
    assert hass.states.get("sensor.web_uptime") is not None

    assert hass.states.get("binary_sensor.web_running").state == "on"
    assert hass.states.get("binary_sensor.web_problem").state == "off"

    assert hass.states.get("switch.web_power").state == "on"

    assert hass.states.get("button.web_stop").state == "unknown"
    assert hass.states.get("button.web_restart").state == "unknown"
    assert hass.states.get("button.web_start").state == "unavailable"


async def test_volume_and_pool_entities(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Volume and storage pool sensors are created."""
    assert hass.states.get("sensor.local_data_used_space").state == "25000000"
    assert hass.states.get("sensor.local_data_total_space").state == "100000000"
    assert hass.states.get("sensor.local_data_usage").state == "25.0"
    assert hass.states.get("sensor.local_data_used_by").state == "1"

    assert (
        hass.states.get("sensor.storage_pool_local_used_space").state == "30000000000"
    )
    assert (
        hass.states.get("sensor.storage_pool_local_free_space").state == "70000000000"
    )
    assert (
        hass.states.get("sensor.storage_pool_local_total_space").state == "100000000000"
    )
    assert hass.states.get("sensor.storage_pool_local_usage").state == "30.0"
    assert hass.states.get("sensor.storage_pool_local_inodes_used").state == "100"
    assert hass.states.get("sensor.storage_pool_local_volumes").state == "1"


async def test_server_entities(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Hub (server) sensors and the refresh button are created."""
    assert hass.states.get("sensor.incus_incus_test_instances_running").state == "1"
    assert hass.states.get("sensor.incus_incus_test_instances_total").state == "1"
    assert hass.states.get("sensor.incus_incus_test_volumes_total").state == "1"
    assert hass.states.get("sensor.incus_incus_test_storage_pools").state == "1"
    assert hass.states.get("sensor.incus_incus_test_server_version").state == "6.0.1"
    assert hass.states.get("sensor.incus_incus_test_api_version").state == "1.0"
    assert hass.states.get("button.incus_incus_test_refresh") is not None


async def test_performance_sensors_can_be_disabled(
    hass: HomeAssistant, fake_client: FakeIncusClient, make_entry
) -> None:
    """Disabling performance sensors keeps only the status sensors."""
    entry = make_entry(options={CONF_ENABLE_PERFORMANCE_SENSORS: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.web_status") is not None
    assert hass.states.get("sensor.web_memory_usage") is None
    assert hass.states.get("sensor.web_cpu_usage") is None


async def test_volume_sensors_can_be_disabled(
    hass: HomeAssistant, fake_client: FakeIncusClient, make_entry
) -> None:
    """Disabling volume sensors removes the volume entities."""
    entry = make_entry(options={CONF_ENABLE_VOLUME_SENSORS: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.local_data_usage") is None
    assert hass.states.get("sensor.web_status") is not None


async def test_refresh_button(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Pressing the refresh button re-reads the server."""
    before = fake_client.calls.count("async_get_server")
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.incus_incus_test_refresh"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake_client.calls.count("async_get_server") > before


async def test_switch_toggles_power(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Turning the switch off/on stops/starts the instance."""
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.web_power"}, blocking=True
    )
    await hass.async_block_till_done()
    assert ("web", "stop") in fake_client.actions

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.web_power"}, blocking=True
    )
    await hass.async_block_till_done()
    assert ("web", "start") in fake_client.actions


async def test_instance_action_button(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Pressing a button runs the matching action."""
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.web_restart"}, blocking=True
    )
    await hass.async_block_till_done()
    assert ("web", "restart") in fake_client.actions
