"""Async client for the Incus REST API.

This is a small, dependency free (aiohttp only) wrapper around the subset of
the Incus REST API that is needed by the integration. It mirrors the behaviour
of the official Go client (``github.com/lxc/incus/client``):

* ``GET /1.0``                                   -> server information
* ``GET /1.0/instances?recursion=2``             -> instances including state
* ``GET /1.0/instances/<name>/state``            -> live instance state
* ``PUT /1.0/instances/<name>/state``            -> start/stop/restart/freeze
* ``GET /1.0/operations/<uuid>/wait``            -> wait for an operation
* ``GET /1.0/storage-pools?recursion=1``         -> storage pools
* ``GET /1.0/storage-pools/<pool>/resources``    -> pool space/inode usage
* ``GET /1.0/storage-pools/<pool>/volumes``      -> volumes (with state)
"""

from __future__ import annotations

import json
import logging
import ssl
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    CONNECTION_TLS,
    CONNECTION_UNIX,
    DEFAULT_PORT,
    DEFAULT_SOCKET_PATH,
)

_LOGGER = logging.getLogger(__name__)

API_VERSION = "1.0"

# How long a plain (non operation) request may take.
DEFAULT_REQUEST_TIMEOUT = 30
# How long we are willing to block while waiting for an operation to finish.
DEFAULT_OPERATION_TIMEOUT = 300


class IncusError(Exception):
    """Base class for all Incus client errors."""


class IncusConnectionError(IncusError):
    """Raised when the Incus server cannot be reached."""


class IncusAuthError(IncusError):
    """Raised when the client is not trusted by the Incus server."""


class IncusAPIError(IncusError):
    """Raised when the Incus server returns an error response."""

    def __init__(
        self,
        message: str,
        error_code: int | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


@dataclass(slots=True)
class IncusConnectionParams:
    """Everything required to reach an Incus server."""

    connection_type: str = CONNECTION_TLS
    host: str | None = None
    port: int = DEFAULT_PORT
    verify_ssl: bool = True
    client_cert: str | None = None
    client_key: str | None = None
    ca_cert: str | None = None
    socket_path: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


def build_ssl_context(params: IncusConnectionParams) -> ssl.SSLContext:
    """Build an :class:`ssl.SSLContext` from the connection parameters.

    The client certificate/key are written to a private temporary file only for
    the duration of :meth:`ssl.SSLContext.load_cert_chain` (which reads them
    eagerly), so no long lived secret is left on disk.
    """
    context = ssl.create_default_context()

    if params.ca_cert:
        try:
            context.load_verify_locations(cadata=params.ca_cert)
        except ssl.SSLError as err:  # pragma: no cover - defensive
            raise IncusConnectionError(f"Invalid CA certificate: {err}") from err

    if not params.verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    if params.client_cert:
        with tempfile.TemporaryDirectory(prefix="incus-cert-") as tmp_dir:
            cert_path = Path(tmp_dir, "client.crt")
            key_path = Path(tmp_dir, "client.key")
            cert_path.write_text(params.client_cert, encoding="utf-8")
            cert_path.chmod(0o600)
            if params.client_key:
                key_path.write_text(params.client_key, encoding="utf-8")
                key_path.chmod(0o600)
            try:
                context.load_cert_chain(
                    certfile=str(cert_path),
                    keyfile=str(key_path) if params.client_key else None,
                )
            except (ssl.SSLError, OSError) as err:
                raise IncusConnectionError(
                    f"Invalid client certificate or key: {err}"
                ) from err

    return context


class IncusClient:
    """A minimal asynchronous Incus API client."""

    def __init__(self, params: IncusConnectionParams) -> None:
        """Initialise the client (does not open a connection yet)."""
        self.params = params
        self._session: aiohttp.ClientSession | None = None
        self._base_url: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_connect(self) -> None:
        """Create the underlying HTTP session/connector."""
        if self._session is not None:
            return

        if self.params.connection_type == CONNECTION_UNIX:
            connector: aiohttp.BaseConnector = aiohttp.UnixConnector(
                path=self.params.socket_path or DEFAULT_SOCKET_PATH,
            )
            # The host component is ignored by the unix connector.
            self._base_url = "http://localhost"
        elif self.params.connection_type == CONNECTION_TLS:
            if not self.params.host:
                raise IncusConnectionError("No host configured for TLS connection")
            ssl_context = build_ssl_context(self.params)
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._base_url = f"https://{self.params.host}:{self.params.port}"
        else:
            raise IncusConnectionError(
                f"Unsupported connection type: {self.params.connection_type}"
            )

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_REQUEST_TIMEOUT),
            headers=self.params.extra_headers,
        )

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Low level plumbing
    # ------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Perform a request and return the decoded Incus response envelope."""
        if self._session is None:
            await self.async_connect()
        assert self._session is not None  # for type checkers

        url = f"{self._base_url}/{API_VERSION}{path}"
        request_timeout = aiohttp.ClientTimeout(
            total=timeout or DEFAULT_REQUEST_TIMEOUT
        )

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=request_timeout,
            ) as response:
                text = await response.text()
                status = response.status
        except TimeoutError as err:
            raise IncusConnectionError(
                f"Timed out talking to Incus at {self._base_url}"
            ) from err
        except (aiohttp.ClientError, OSError) as err:
            raise IncusConnectionError(
                f"Error connecting to Incus at {self._base_url}: {err}"
            ) from err

        if status in (401, 403):
            raise IncusAuthError(
                "The Incus server refused the request. Make sure the client "
                "certificate is trusted (e.g. 'incus config trust add')."
            )

        try:
            payload: dict[str, Any] = json.loads(text) if text else {}
        except ValueError as err:
            raise IncusError(
                f"Invalid JSON response from Incus (HTTP {status}): {text[:200]}"
            ) from err

        if payload.get("type") == "error" or status >= 400:
            raise IncusAPIError(
                payload.get("error") or f"HTTP {status}",
                error_code=payload.get("error_code"),
                status_code=payload.get("status_code", status),
            )

        return payload

    @staticmethod
    def _metadata(payload: dict[str, Any]) -> Any:
        return payload.get("metadata")

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    async def async_get_server(self) -> dict[str, Any]:
        """Return the (trusted) server information."""
        payload = await self._request("GET", "")
        metadata = self._metadata(payload) or {}
        auth = metadata.get("auth")
        if auth == "untrusted":
            raise IncusAuthError(
                "The Incus server does not trust this client certificate"
            )
        return metadata

    # ------------------------------------------------------------------
    # Instances
    # ------------------------------------------------------------------
    async def async_get_instances(
        self, *, all_projects: bool = False, recursion: int = 2
    ) -> list[dict[str, Any]]:
        """Return a list of instances (with state when ``recursion >= 2``)."""
        params: dict[str, Any] = {"recursion": str(recursion)}
        if all_projects:
            params["all-projects"] = "true"
        payload = await self._request("GET", "/instances", params=params)
        return self._metadata(payload) or []

    async def async_get_instance_state(
        self, name: str, *, project: str | None = None
    ) -> dict[str, Any]:
        """Return the live state of a single instance."""
        params = {"project": project} if project else None
        payload = await self._request(
            "GET", f"/instances/{quote(name, safe='')}/state", params=params
        )
        return self._metadata(payload) or {}

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
        """Change the runtime state of an instance and wait for completion."""
        params = {"project": project} if project else None
        body = {
            "action": action,
            "timeout": timeout,
            "force": force,
            "stateful": stateful,
        }
        payload = await self._request(
            "PUT",
            f"/instances/{quote(name, safe='')}/state",
            params=params,
            json_body=body,
        )

        metadata = self._metadata(payload) or {}
        if payload.get("type") == "async" and metadata.get("id"):
            wait_timeout = timeout + 60 if timeout and timeout > 0 else 120
            return await self.async_wait_operation(
                metadata["id"], timeout=wait_timeout, project=project
            )
        return metadata

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    async def async_wait_operation(
        self,
        operation_id: str,
        *,
        timeout: int = DEFAULT_OPERATION_TIMEOUT,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Block until an operation finishes and raise on failure."""
        params: dict[str, Any] = {"timeout": timeout}
        if project:
            params["project"] = project
        payload = await self._request(
            "GET",
            f"/operations/{quote(operation_id, safe='')}/wait",
            params=params,
            timeout=timeout + 30,
        )
        operation = self._metadata(payload) or {}
        if operation.get("err"):
            raise IncusAPIError(
                operation["err"], status_code=operation.get("status_code")
            )
        if operation.get("status_code") not in (None, 200):
            raise IncusAPIError(
                f"Operation finished with status {operation.get('status')}",
                status_code=operation.get("status_code"),
            )
        return operation

    # ------------------------------------------------------------------
    # Storage pools and volumes
    # ------------------------------------------------------------------
    async def async_get_storage_pools(self) -> list[dict[str, Any]]:
        """Return all storage pools."""
        payload = await self._request(
            "GET", "/storage-pools", params={"recursion": "1"}
        )
        return self._metadata(payload) or []

    async def async_get_storage_pool_resources(self, pool: str) -> dict[str, Any]:
        """Return space/inode usage for a storage pool."""
        payload = await self._request(
            "GET", f"/storage-pools/{quote(pool, safe='')}/resources"
        )
        return self._metadata(payload) or {}

    async def async_get_storage_pool_volumes(
        self,
        pool: str,
        *,
        all_projects: bool = False,
        recursion: int = 2,
    ) -> list[dict[str, Any]]:
        """Return the volumes of a storage pool.

        ``recursion=2`` returns ``StorageVolumeFull`` objects which embed the
        live ``state`` (used/total bytes) for each volume.
        """
        params: dict[str, Any] = {"recursion": str(recursion)}
        if all_projects:
            params["all-projects"] = "true"
        payload = await self._request(
            "GET", f"/storage-pools/{quote(pool, safe='')}/volumes", params=params
        )
        return self._metadata(payload) or []

    async def async_get_storage_pool_volume_state(
        self, pool: str, volume_type: str, name: str, *, project: str | None = None
    ) -> dict[str, Any]:
        """Return the live state of a single storage volume."""
        params = {"project": project} if project else None
        payload = await self._request(
            "GET",
            (
                f"/storage-pools/{quote(pool, safe='')}/volumes/"
                f"{quote(volume_type, safe='')}/{quote(name, safe='')}/state"
            ),
            params=params,
        )
        return self._metadata(payload) or {}

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    async def async_get_metrics(self) -> str:
        """Return the raw OpenMetrics text exposition (``GET /1.0/metrics``)."""
        if self._session is None:
            await self.async_connect()
        assert self._session is not None
        url = f"{self._base_url}/{API_VERSION}/metrics"
        try:
            async with self._session.get(url) as response:
                if response.status in (401, 403):
                    raise IncusAuthError("Not authorised to read metrics")
                response.raise_for_status()
                return await response.text()
        except (aiohttp.ClientError, OSError) as err:
            raise IncusConnectionError(f"Error fetching metrics: {err}") from err
