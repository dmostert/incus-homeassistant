# Incus for Home Assistant

[![Hassfest](https://github.com/dmostert/incus-homeassistant/actions/workflows/hassfest.yml/badge.svg)](https://github.com/dmostert/incus-homeassistant/actions/workflows/hassfest.yml)
[![Validate](https://github.com/dmostert/incus-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/dmostert/incus-homeassistant/actions/workflows/validate.yml)
[![Tests](https://github.com/dmostert/incus-homeassistant/actions/workflows/tests.yml/badge.svg)](https://github.com/dmostert/incus-homeassistant/actions/workflows/tests.yml)

A Home Assistant custom integration for [Incus](https://linuxcontainers.org/incus/),
the system container and virtual machine manager. It talks directly to the Incus
REST API and lets you monitor and control your instances, storage pools and
storage volumes from Home Assistant.

## Features

- **Control instances** — start, stop, restart, freeze and unfreeze containers
  and virtual machines.
- **Statistics** — CPU, memory, disk and network metrics per instance, plus
  capacity/usage for storage pools and volumes.
- **Dynamic discovery** — new instances, storage pools and volumes appear
  automatically after a refresh; removed ones disappear.
- **Two connection methods** — a remote HTTPS endpoint authenticated with a
  client certificate, or a local Unix socket.
- **Pure Python** — no external binaries; only `aiohttp` (bundled with Home
  Assistant) is used.

## Installation

### HACS (custom repository)

1. Open HACS → **Integrations** → the three-dot menu → **Custom repositories**.
2. Add `https://github.com/dmostert/incus-homeassistant` with category
   **Integration**.
3. Install **Incus** and restart Home Assistant.

### Manual

Copy `custom_components/incus` into your Home Assistant `config` directory and
restart Home Assistant:

```
config/
└── custom_components/
    └── incus/
```

## Configuration

Add the integration from **Settings → Devices & Services → Add Integration →
Incus** and pick a connection method.

### Remote server (HTTPS + client certificate)

Incus only allows API access to trusted clients. Generate a client certificate
and key, then trust it on the server:

```bash
# Create a certificate/key pair (or reuse an existing one)
openssl req -x509 -newkey rsa:2048 -nodes -keyout client.key -out client.crt -days 3650 -subj "/CN=home-assistant"

# Trust it on the Incus server
incus config trust add-certificate client.crt
```

Make sure the Incus server is listening on the network:

```bash
incus config set core.https_address :8443
```

Then enter the host, port (default `8443`), the client certificate and its
private key. An optional custom CA certificate can be supplied if the server
certificate is not signed by a public CA.

### Local Unix socket

If Home Assistant runs on the same host as Incus (for example when HA runs in a
container with the Incus socket mounted), choose **Connect over Unix socket** and
provide the socket path. The default is `/var/lib/incus/unix.socket`.

## Entities

For every instance the integration creates a device with:

| Platform | Entities |
| --- | --- |
| `sensor` | Status, CPU usage, Memory usage / percent / total / peak, Swap usage, Processes, Disk usage / total / read / written, Network received / sent, Uptime, IP address, Instance type |
| `binary_sensor` | Running, Problem |
| `switch` | Power (start/stop) |
| `button` | Start, Stop, Restart |

Storage pools get a device with used/free/total space, usage percentage, inode
counters and the number of volumes. Storage volumes get a device with used and
total space, usage percentage and a "used by" counter.

The server itself is exposed as a hub device with the running/total instance
counts, volume and pool counts, server/API/kernel versions, storage driver and a
**Refresh** button.

Performance sensors (CPU, memory, disk, network) can be disabled in the options
to reduce polling load; only the status/capacity sensors remain.

## Options

Open the integration's **Configure** dialog to change:

- **Update interval** — how often the server is polled (seconds).
- **Include all projects** — discover instances and volumes from every Incus
  project instead of only the default one.
- **Instance / storage volume / storage pool sensors** — toggle sensor groups.
- **Performance sensors** — enable or disable the CPU/memory/disk/network
  metrics.

## Services

| Service | Description |
| --- | --- |
| `incus.start_instance` | Start an instance. |
| `incus.stop_instance` | Stop an instance. |
| `incus.restart_instance` | Restart an instance. |
| `incus.freeze_instance` | Freeze (pause) a running instance. |
| `incus.unfreeze_instance` | Unfreeze (resume) a frozen instance. |
| `incus.refresh` | Re-read the server, picking up new instances and volumes. |

All instance services accept `instance` (name), optional `project`, `force`,
`timeout` and `entry_id` (to target one server when several are configured).

## Troubleshooting

- **"The Incus server does not trust this client certificate"** — the client
  certificate has not been added to the server. Run
  `incus config trust add-certificate <cert>` (or `incus config trust add`).
- **"Failed to connect to the Incus server"** — check the host/port and that
  `core.https_address` is set, or verify the Unix socket path and that it is
  reachable from the Home Assistant process.
- Enable debug logging for more detail:

  ```yaml
  logger:
    logs:
      custom_components.incus: debug
  ```

## Releasing

HACS uses the **tag name of the latest GitHub release** as the version. If no
release exists it falls back to the first 7 characters of the last commit, which
is why an unreleased repository shows a commit hash as its version.

To publish a new version:

1. Bump `version` in `custom_components/incus/manifest.json`.
2. Commit and push to `main`.

The [`Release`](.github/workflows/release.yml) workflow then creates the matching
`v<version>` tag and GitHub release automatically (it skips if the release
already exists). Alternatively, create a release manually with
`gh release create v<version> --generate-notes`.

## License

[MIT](LICENSE)
