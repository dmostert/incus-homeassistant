"""Constants for the Incus integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "incus"
NAME: Final = "Incus"
MANUFACTURER: Final = "Linux Containers"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_CLIENT_CERT: Final = "client_cert"
CONF_CLIENT_KEY: Final = "client_key"
CONF_CA_CERT: Final = "ca_cert"
CONF_SOCKET_PATH: Final = "socket_path"

CONNECTION_TLS: Final = "tls"
CONNECTION_UNIX: Final = "unix"

CONNECTION_TYPES: Final = [CONNECTION_TLS, CONNECTION_UNIX]

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_ALL_PROJECTS: Final = "all_projects"
CONF_ENABLE_INSTANCE_SENSORS: Final = "enable_instance_sensors"
CONF_ENABLE_VOLUME_SENSORS: Final = "enable_volume_sensors"
CONF_ENABLE_POOL_SENSORS: Final = "enable_pool_sensors"
CONF_ENABLE_PERFORMANCE_SENSORS: Final = "enable_performance_sensors"

DEFAULT_PORT: Final = 8443
DEFAULT_SOCKET_PATH: Final = "/var/lib/incus/unix.socket"
DEFAULT_UPDATE_INTERVAL: Final = 30
MIN_UPDATE_INTERVAL: Final = 5
MAX_UPDATE_INTERVAL: Final = 3600

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_START_INSTANCE: Final = "start_instance"
SERVICE_STOP_INSTANCE: Final = "stop_instance"
SERVICE_RESTART_INSTANCE: Final = "restart_instance"
SERVICE_FREEZE_INSTANCE: Final = "freeze_instance"
SERVICE_UNFREEZE_INSTANCE: Final = "unfreeze_instance"
SERVICE_REFRESH: Final = "refresh"

ATTR_INSTANCE: Final = "instance"
ATTR_PROJECT: Final = "project"
ATTR_FORCE: Final = "force"
ATTR_TIMEOUT: Final = "timeout"
ATTR_ENTRY_ID: Final = "entry_id"

# ---------------------------------------------------------------------------
# Instance actions
# ---------------------------------------------------------------------------
ACTION_START: Final = "start"
ACTION_STOP: Final = "stop"
ACTION_RESTART: Final = "restart"
ACTION_FREEZE: Final = "freeze"
ACTION_UNFREEZE: Final = "unfreeze"

# ---------------------------------------------------------------------------
# Instance status values reported by the Incus API
# ---------------------------------------------------------------------------
STATUS_RUNNING: Final = "Running"
STATUS_STOPPED: Final = "Stopped"
STATUS_FROZEN: Final = "Frozen"
STATUS_ERROR: Final = "Error"

ACTIVE_STATUSES: Final = (STATUS_RUNNING, STATUS_FROZEN)
