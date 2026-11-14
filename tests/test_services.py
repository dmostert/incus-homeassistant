"""Tests for the Incus service handlers."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.incus.const import DOMAIN
from custom_components.incus.incus_client import IncusAPIError

from .conftest import FakeIncusClient


@pytest.mark.parametrize(
    ("service", "action"),
    [
        ("start_instance", "start"),
        ("stop_instance", "stop"),
        ("restart_instance", "restart"),
        ("freeze_instance", "freeze"),
        ("unfreeze_instance", "unfreeze"),
    ],
)
async def test_instance_services(
    hass: HomeAssistant,
    fake_client: FakeIncusClient,
    setup_entry: MockConfigEntry,
    service: str,
    action: str,
) -> None:
    """Each instance service maps to the matching Incus action."""
    await hass.services.async_call(DOMAIN, service, {"instance": "web"}, blocking=True)
    await hass.async_block_till_done()
    assert ("web", action) in fake_client.actions


async def test_unknown_instance(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Calling a service for an unknown instance raises."""
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "start_instance", {"instance": "nope"}, blocking=True
        )


async def test_service_action_error(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """A client error is surfaced as a HomeAssistantError."""
    fake_client.action_error = IncusAPIError("boom")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "start_instance", {"instance": "web"}, blocking=True
        )


async def test_refresh_service(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """The refresh service re-reads the server."""
    before = fake_client.calls.count("async_get_server")
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()
    assert fake_client.calls.count("async_get_server") > before


async def test_services_removed_on_unload(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry: MockConfigEntry
) -> None:
    """Unloading the last entry removes the services."""
    assert hass.services.has_service(DOMAIN, "start_instance")
    await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "start_instance")
    assert not hass.services.has_service(DOMAIN, "refresh")
