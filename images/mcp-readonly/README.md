# mcp-readonly

Read-only MCP server (streamable HTTP on :8000, path `/mcp`) for the lab:
Kubernetes, MariaDB replica, Kafka, and the NFS datafiles share. Deployed by
`k8s/mcp/`, exposed through Tailscale Funnel, authenticated per client with
bearer tokens.

## Tools

| Area | Tools |
|------|-------|
| Kubernetes | `k8s_list`, `k8s_get`, `k8s_top` (no secrets; env values redacted) |
| MariaDB | `db_query` (single SELECT/SHOW/DESCRIBE/EXPLAIN), `db_schema` |
| Kafka | `kafka_list_topics`, `kafka_describe_topic`, `kafka_read_messages` (max 50, values truncated, no offset commits) |
| NFS | `nfs_list`, `nfs_stat`, `nfs_find` (names and metadata only, never file contents) |

## Configuration (env)

| Variable | Source |
|----------|--------|
| `MCP_TOKEN_<NAME>` (one per client) | secret `mcp-tokens` |
| `MARIADB_HOST/PORT`, `MARIADB_USER/PW` | manifest + secret `mcp-mariadb` |
| `KAFKA_BOOTSTRAP`, `KAFKA_USER/PW`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_SASL_MECHANISM` | manifest + secret `mcp-kafka` |
| `NFS_ROOT` | manifest (`/data/datafiles`) |

Startup refuses to run with no `MCP_TOKEN_*` set. Every tool call and failed
auth is logged (client name, tool, arguments) to stdout.

## Layers of read-only enforcement

The tool guards are defence in depth. The real controls are the credentials
and mounts: the ClusterRole (no secrets, no writes), a SELECT-only DB user on
mdb3, Kafka ACLs, and the `ro` NFS mount.

## Develop and test

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
```

## Build and push

Needs Artifact Registry **writer** credentials (nodes only have Reader):

```bash
gcloud auth configure-docker northamerica-northeast2-docker.pkg.dev
docker buildx build --platform linux/arm64,linux/amd64 \
  -t northamerica-northeast2-docker.pkg.dev/cutlernet-datahub/datahub-pr/mcp-readonly:0.1.0 \
  --push .
```

Bump the tag here and in `k8s/mcp/50-mcp-server.yaml` together.

## Updating dependencies

`mcp` is pinned `<2`: v2 renamed `FastMCP` to `MCPServer`, and this code uses
the v1 API. To refresh the lock file, rebuild a clean venv from
`requirements.in`, run `pip freeze`, re-run the tests, then rebuild the image.
