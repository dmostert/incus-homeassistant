"""Tests for the Incus config and options flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.incus.const import (
    CONF_ALL_PROJECTS,
    CONF_CA_CERT,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_CONNECTION_TYPE,
    CONF_ENABLE_INSTANCE_SENSORS,
    CONF_ENABLE_PERFORMANCE_SENSORS,
    CONF_ENABLE_POOL_SENSORS,
    CONF_ENABLE_VOLUME_SENSORS,
    CONF_HOST,
    CONF_PORT,
    CONF_SOCKET_PATH,
    CONF_UPDATE_INTERVAL,
    CONF_VERIFY_SSL,
    CONNECTION_TLS,
    CONNECTION_UNIX,
    DOMAIN,
)
from custom_components.incus.incus_client import (
    IncusAPIError,
    IncusAuthError,
    IncusConnectionError,
    IncusError,
)

from .conftest import FakeIncusClient

STRINGS = json.loads(
    (
        Path(__file__).resolve().parents[1] / "custom_components/incus/strings.json"
    ).read_text()
)


def _menu_keys(result: dict) -> set[str]:
    """Return the option keys of a menu flow result."""
    return {
        option["value"] if isinstance(option, dict) else option
        for option in result["menu_options"]
    }


async def _start(hass: HomeAssistant) -> dict:
    """Start the config flow at the user (menu) step."""
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def _choose(hass: HomeAssistant, flow_id: str, step: str) -> dict:
    """Pick an option from the menu step."""
    return await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": step}
    )


def test_user_step_translations_present() -> None:
    """The user menu step must translate every menu option."""
    menu = STRINGS["config"]["step"]["user"]["menu_options"]
    assert set(menu) == {"tls", "unix"}
    assert all(label for label in menu.values())


async def test_user_menu(hass: HomeAssistant) -> None:
    """The first step offers the two connection methods."""
    result = await _start(hass)
    assert result["type"] == "menu"
    assert result["step_id"] == "user"
    assert _menu_keys(result) == {"tls", "unix"}


async def test_tls_flow_success(
    hass: HomeAssistant, fake_client: FakeIncusClient
) -> None:
    """A valid TLS configuration creates an entry."""
    result = await _start(hass)
    result = await _choose(hass, result["flow_id"], "tls")
    assert result["type"] == "form"
    assert result["step_id"] == "tls"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "incus.local",
            CONF_PORT: 8443,
            CONF_VERIFY_SSL: True,
            CONF_CLIENT_CERT: "-----BEGIN CERT-----",
            CONF_CLIENT_KEY: "-----BEGIN KEY-----",
            CONF_CA_CERT: "",
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "incus-test"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_CONNECTION_TYPE] == CONNECTION_TLS
    assert entry.data[CONF_HOST] == "incus.local"
    assert entry.unique_id == "deadbeef"


async def test_unix_flow_success(
    hass: HomeAssistant, fake_client: FakeIncusClient
) -> None:
    """A valid Unix socket configuration creates an entry."""
    fake_client.server_raw["environment"].pop("certificate_fingerprint")

    result = await _start(hass)
    result = await _choose(hass, result["flow_id"], "unix")
    assert result["type"] == "form"
    assert result["step_id"] == "unix"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOCKET_PATH: "/var/lib/incus/unix.socket"}
    )
    assert result["type"] == "create_entry"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_CONNECTION_TYPE] == CONNECTION_UNIX
    assert entry.unique_id == "unix:/var/lib/incus/unix.socket"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (IncusConnectionError("boom"), "cannot_connect"),
        (IncusAuthError("nope"), "invalid_auth"),
        (IncusAPIError("nope"), "api_error"),
        (IncusError("nope"), "unknown"),
    ],
)
async def test_tls_flow_errors(
    hass: HomeAssistant,
    fake_client: FakeIncusClient,
    error: Exception,
    expected: str,
) -> None:
    """Connection problems are reported on the form."""
    fake_client.server_error = error
    result = await _start(hass)
    result = await _choose(hass, result["flow_id"], "tls")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "incus.local",
            CONF_PORT: 8443,
            CONF_VERIFY_SSL: True,
            CONF_CLIENT_CERT: "cert",
            CONF_CLIENT_KEY: "",
            CONF_CA_CERT: "",
        },
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": expected}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_tls_flow_already_configured(
    hass: HomeAssistant, fake_client: FakeIncusClient, config_entry
) -> None:
    """A server with the same certificate fingerprint is rejected."""
    config_entry.add_to_hass(hass)

    result = await _start(hass)
    result = await _choose(hass, result["flow_id"], "tls")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "incus.local",
            CONF_PORT: 8443,
            CONF_VERIFY_SSL: True,
            CONF_CLIENT_CERT: "cert",
            CONF_CLIENT_KEY: "",
            CONF_CA_CERT: "",
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_options_flow(
    hass: HomeAssistant, fake_client: FakeIncusClient, setup_entry
) -> None:
    """The options flow stores the chosen options."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 60,
            CONF_ALL_PROJECTS: True,
            CONF_ENABLE_INSTANCE_SENSORS: True,
            CONF_ENABLE_VOLUME_SENSORS: False,
            CONF_ENABLE_POOL_SENSORS: True,
            CONF_ENABLE_PERFORMANCE_SENSORS: False,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    assert setup_entry.options[CONF_UPDATE_INTERVAL] == 60
    assert setup_entry.options[CONF_ALL_PROJECTS] is True
    assert setup_entry.options[CONF_ENABLE_VOLUME_SENSORS] is False
    assert setup_entry.state is ConfigEntryState.LOADED
