"""Config and options flow for the Incus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
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
    DEFAULT_PORT,
    DEFAULT_SOCKET_PATH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    NAME,
)
from .incus_client import (
    IncusAPIError,
    IncusAuthError,
    IncusClient,
    IncusConnectionError,
    IncusConnectionParams,
    IncusError,
)

_LOGGER = logging.getLogger(__name__)

_PEM_TEXT = TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT))
_PEM_SECRET = TextSelector(
    TextSelectorConfig(multiline=True, type=TextSelectorType.PASSWORD)
)

TLS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean,
        vol.Required(CONF_CLIENT_CERT): _PEM_TEXT,
        vol.Optional(CONF_CLIENT_KEY, default=""): _PEM_SECRET,
        vol.Optional(CONF_CA_CERT, default=""): _PEM_TEXT,
    }
)

UNIX_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOCKET_PATH, default=DEFAULT_SOCKET_PATH): cv.string,
    }
)


async def _async_validate_connection(
    hass: HomeAssistant, params: IncusConnectionParams
) -> tuple[str, str]:
    """Validate the connection and return (title, unique_id)."""
    client = IncusClient(params)
    try:
        await client.async_connect()
        server = await client.async_get_server()
    finally:
        await client.close()

    environment: dict[str, Any] = server.get("environment") or {}
    title = environment.get("server_name") or params.host or NAME

    fingerprint = environment.get("certificate_fingerprint")
    if fingerprint:
        unique_id = fingerprint
    elif params.connection_type == CONNECTION_UNIX:
        unique_id = f"unix:{params.socket_path}"
    else:
        unique_id = f"{params.host}:{params.port}"

    return title, unique_id


class IncusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Incus config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user how they want to connect."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[CONNECTION_TLS, CONNECTION_UNIX],
        )

    async def async_step_tls(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a TLS (remote) connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            params = IncusConnectionParams(
                connection_type=CONNECTION_TLS,
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                verify_ssl=user_input[CONF_VERIFY_SSL],
                client_cert=user_input.get(CONF_CLIENT_CERT) or None,
                client_key=user_input.get(CONF_CLIENT_KEY) or None,
                ca_cert=user_input.get(CONF_CA_CERT) or None,
            )
            try:
                title, unique_id = await _async_validate_connection(self.hass, params)
            except IncusAuthError:
                errors["base"] = "invalid_auth"
            except IncusConnectionError:
                errors["base"] = "cannot_connect"
            except IncusAPIError as err:
                errors["base"] = "api_error"
                _LOGGER.debug("Incus API error during setup: %s", err)
            except IncusError as err:
                errors["base"] = "unknown"
                _LOGGER.exception("Unexpected Incus error during setup: %s", err)
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TLS,
                        **user_input,
                    },
                )

        return self.async_show_form(
            step_id="tls", data_schema=TLS_SCHEMA, errors=errors
        )

    async def async_step_unix(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a local Unix socket connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            params = IncusConnectionParams(
                connection_type=CONNECTION_UNIX,
                socket_path=user_input[CONF_SOCKET_PATH],
            )
            try:
                title, unique_id = await _async_validate_connection(self.hass, params)
            except IncusAuthError:
                errors["base"] = "invalid_auth"
            except IncusConnectionError:
                errors["base"] = "cannot_connect"
            except IncusAPIError as err:
                errors["base"] = "api_error"
                _LOGGER.debug("Incus API error during setup: %s", err)
            except IncusError as err:
                errors["base"] = "unknown"
                _LOGGER.exception("Unexpected Incus error during setup: %s", err)
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_UNIX,
                        **user_input,
                    },
                )

        return self.async_show_form(
            step_id="unix", data_schema=UNIX_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return IncusOptionsFlow()


class IncusOptionsFlow(OptionsFlow):
    """Handle the Incus options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
                vol.Optional(
                    CONF_ALL_PROJECTS,
                    default=options.get(CONF_ALL_PROJECTS, False),
                ): cv.boolean,
                vol.Optional(
                    CONF_ENABLE_INSTANCE_SENSORS,
                    default=options.get(CONF_ENABLE_INSTANCE_SENSORS, True),
                ): cv.boolean,
                vol.Optional(
                    CONF_ENABLE_VOLUME_SENSORS,
                    default=options.get(CONF_ENABLE_VOLUME_SENSORS, True),
                ): cv.boolean,
                vol.Optional(
                    CONF_ENABLE_POOL_SENSORS,
                    default=options.get(CONF_ENABLE_POOL_SENSORS, True),
                ): cv.boolean,
                vol.Optional(
                    CONF_ENABLE_PERFORMANCE_SENSORS,
                    default=options.get(CONF_ENABLE_PERFORMANCE_SENSORS, True),
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
