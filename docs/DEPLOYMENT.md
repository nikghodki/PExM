# Deployment

ContextOS ships with three deployment paths: Docker Compose (local dev /
small deployments), a single-container Docker image, and Kubernetes (Helm).

## Docker Compose (full local stack)

```bash
docker-compose up -d
```

Starts ContextOS, Kafka, Zookeeper, Prometheus, Grafana, and Jaeger.

| Service | URL |
|---|---|
| gRPC | `localhost:50051` |
| Grafana (admin/admin) | http://localhost:3000 |
| Prometheus | http://localhost:9091 |
| Jaeger UI | http://localhost:16686 |
| Kafka | `localhost:9092` |

Stop with `docker-compose down -v`.

## Single container

```bash
docker build -t contextos/server .
docker run -d \
  -p 50051:50051 \
  -v "$PWD/contextos-data:/data" \
  -e CONTEXTOS_LOG=info \
  contextos/server
```

The image is multi-stage (`Dockerfile`): a `rust:slim-bookworm` builder
installs `protobuf-compiler` and builds the `contextos-server` and `ctx`
binaries, then a `debian:bookworm-slim` runtime runs them as a non-root user.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `CONTEXTOS_BIND` | `0.0.0.0:50051` | gRPC listen address |
| `CONTEXTOS_ROCKSDB_PATH` | `/data/rocksdb` | RocksDB data directory |
| `CONTEXTOS_LOG` | `info` | Log level |
| `KAFKA_BROKERS` | `kafka:9092` | Bus Kafka brokers |

## Kubernetes

Manifests live in `deploy/k8s/` (namespace, deployment, service, HPA,
configmap). The Helm chart in `deploy/helm/contextos/` packages the same with
values for replication, resources, and the service port.

```bash
helm install contextos ./deploy/helm/contextos
```

> The observability configs in `deploy/observability/` are consumed by the
> Compose stack. For a managed Prometheus/Grafana in-cluster, point them at
> the `9090` metrics port exposed by the server container.

## Observability

The Compose stack starts Prometheus, Grafana, and Jaeger and the configs for
all three ship in `deploy/observability/`:

- **Prometheus** — `deploy/observability/prometheus.yml`
- **Grafana dashboard** — `deploy/observability/grafana-dashboard.json`
- **Jaeger** — `deploy/observability/jaeger-config.yaml`

> **Status:** the observability *infrastructure* and configs are complete and
> tested to start, but the server does not yet expose its own Prometheus
> `/metrics` endpoint on port `9090`. That exposition is a Phase-3 item (see
> the roadmap in the [README](../README.md)); the `metrics` and
> `metrics-exporter-prometheus` crates are already declared in the workspace
> for when it lands. The server currently exposes the gRPC port (`50051`) and
> a health-check service.
