# xrepomirror

A CLI tool to mirror Docker images and Helm charts from public registries to local/private repositories. Designed for air-gapped or restricted environments where workloads cannot pull directly from the internet.

---

## Features

- Mirror Docker images via `docker pull` / `docker tag` / `docker push`
- Mirror Helm charts via `helm pull` / `helm push` (OCI) or Nexus 3 REST API upload
- Proxy support via configurable environment variables
- Single `sources.yaml` configuration file for all sources and destinations
- Supports Python 3.6 and above

---

## Requirements

- Python 3.6+
- `docker` CLI — available and authenticated to the destination registry
- `helm` CLI (v3) — available and authenticated to the destination registry (for Helm mirroring)

---

## Installation

```bash
pip install xrepomirror
```

Or install from source:

```bash
git clone https://github.com/tkdpython/xrepomirror.git
cd xrepomirror
pip install .
```

---

## Configuration

Create a `sources.yaml` file in your working directory. The file has two top-level keys: `sources` and `settings`.

### Full example

```yaml
sources:
  docker_images:
    - source: docker.io/grafana/grafana:12.3.0
    - source: ghcr.io/grafana/grafana-operator:v5.21.3
    - source: quay.io/prometheus/prometheus:v3.9.1

  helm_charts:
    - chart: kube-prometheus-stack
      repo: https://prometheus-community.github.io/helm-charts
      version: 80.13.3
    - chart: grafana-operator
      repo: https://grafana.github.io/helm-charts
      version: 5.21.4

settings:
  destination_repositories:
    docker:
      repo: ctr.example.com
    helm:
      repo: repo.example.com/helm
      type: nexus3   # "nexus3" or "oci" (default: "oci")
  env_vars:
    HTTP_PROXY: http://proxy.local:8080
    HTTPS_PROXY: http://proxy.local:8080
    NO_PROXY: .mycompany.co.uk,.svc,.local,localhost
```

### `sources`

| Key | Description |
| --- | --- |
| `docker_images` | List of Docker image references to mirror. Each entry requires a `source` key with the full image reference including tag. |
| `helm_charts` | List of Helm charts to mirror. Each entry requires `chart` (chart name), `repo` (upstream Helm repo URL), and `version`. |

### `settings`

| Key | Description |
| --- | --- |
| `destination_repositories.docker.repo` | Destination Docker registry host/prefix (e.g. `ctr.example.com`). |
| `destination_repositories.helm.repo` | Destination Helm repository. For OCI this is the registry path; for Nexus 3 this is `<host>/<repo-name>`. |
| `destination_repositories.helm.type` | How to upload Helm charts — `"oci"` (default, uses `helm push`) or `"nexus3"` (uses the Nexus 3 REST API). |
| `env_vars` | Key/value pairs to set as environment variables before any operations. Existing variables are not overwritten, so values can be overridden at runtime. |

---

## Usage

```text
xrepomirror [--sources FILE] [--skip-docker] [--skip-helm]
```

| Flag | Description |
| --- | --- |
| `--sources FILE` | Path to the sources YAML file (default: `sources.yaml` in the current directory). |
| `--skip-docker` | Skip mirroring Docker images. |
| `--skip-helm` | Skip mirroring Helm charts. |
| `--version` | Print the version and exit. |

### Examples

Mirror everything using the default `sources.yaml`:

```bash
xrepomirror
```

Mirror only Helm charts:

```bash
xrepomirror --skip-docker
```

Mirror only Docker images using a custom config file:

```bash
xrepomirror --sources /path/to/my-sources.yaml --skip-helm
```

---

## Docker image destination naming

The destination image reference is derived from the source by taking the last path segment (image name and tag) and prefixing it with the configured destination registry. For example:

| Source | Destination (`ctr.example.com`) |
| --- | --- |
| `docker.io/grafana/grafana:12.3.0` | `ctr.example.com/grafana:12.3.0` |
| `ghcr.io/grafana/grafana-operator:v5.21.3` | `ctr.example.com/grafana-operator:v5.21.3` |
| `quay.io/prometheus/prometheus:v3.9.1` | `ctr.example.com/prometheus:v3.9.1` |

---

## Helm destination types

### OCI (default)

Charts are pushed using `helm push` to an OCI-compatible registry:

```yaml
settings:
  destination_repositories:
    helm:
      repo: ctr.example.com/helm-charts
      type: oci
```

### Nexus 3

Charts are uploaded via the Nexus 3 REST API (`POST /service/rest/v1/components`). The `repo` value must be in the format `<host>/<repository-name>`:

```yaml
settings:
  destination_repositories:
    helm:
      repo: repo.example.com/helm
      type: nexus3
```

---

## Proxy support

Set `env_vars` in `sources.yaml` to inject proxy settings before any network operations. Standard proxy variables are supported: `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` (and their lowercase equivalents). Variables that are already set in the shell environment take precedence over values in `sources.yaml`.

---

## Dependencies

| Package | Purpose |
| --- | --- |
| `PyYAML>=5.1` | Parsing `sources.yaml` |
| `requests>=2.20.0` | Nexus 3 REST API uploads |

---

## License

MIT
