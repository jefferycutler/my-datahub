# Read-only MCP gateway (Kubernetes)

Public entry for Claude/Gemini via Tailscale Funnel, terminating in a
locked-down `mcp-server` pod that can read: the Kubernetes API, the MariaDB
replica (mdb3), Kafka topics/messages, and the NAS datafiles share.

```
Internet -> Tailscale Funnel -> proxy pod (ns: tailscale)
         -> mcp-server Service :8000 (ns: mcp-server) -> k8s API / mdb3 / Kafka / NFS
```

Both namespaces are default-deny. The proxy can reach only `mcp-server:8000`
(plus Tailscale on the public internet, never RFC1918). `mcp-server` accepts
ingress only from the `tailscale` namespace.

## Files

| File | Purpose |
|------|---------|
| `00-namespaces.yaml` | `tailscale` (baseline PSS), `mcp-server` (restricted PSS) |
| `10-netpol-mcp-server.yaml` | default-deny + allows: DNS, k8s API, mdb3:3306, Kafka:9092 |
| `11-netpol-tailscale.yaml` | default-deny + allows: DNS, API, mcp-server:8000, Tailscale egress |
| `20-rbac.yaml` | read-only ClusterRole (no secrets, no pods/log, no writes) |
| `30-quota.yaml` | ResourceQuota + LimitRange |
| `40-nfs-readonly.yaml` | read-only PV/PVC for `area51nas1:/mnt/datahub/datafiles` |
| `50-mcp-server.yaml` | Deployment + ClusterIP Service |
| `60-funnel-ingress.yaml` | Tailscale Ingress with Funnel enabled |
| `../tailscale-operator/values.yaml` | Helm values for the operator |

## Prerequisites (not in git)

1. **Tailscale ACLs**: define `tag:k8s-operator` and `tag:mcp-edge`
   (operator owns the edge tag), grant `funnel` to `tag:mcp-edge` via
   `nodeAttrs`, and give `tag:mcp-edge` no access to the NAS, subnet routes
   or other devices.
2. **Tailscale OAuth client** (tag `tag:k8s-operator`; scopes devices:core
   write, auth_keys write).
3. **MariaDB**: SELECT-only user, host-restricted, created on the primary and
   replicated to mdb3.
4. **Kafka**: dedicated SCRAM user with Describe + Read ACLs (not the shared
   consumer user).
5. **Image**: multi-arch (arm64 + amd64) build pushed to
   `northamerica-northeast2-docker.pkg.dev/cutlernet-datahub/datahub-pr/mcp-readonly`;
   the tag must match `50-mcp-server.yaml`. Pushing needs writer credentials
   (the node Reader account can only pull).
6. **Network policy enforcement**: confirm K3s enforces policies (see Verify).

## Secrets

Never committed. Create after the namespaces exist:

```bash
kubectl -n tailscale create secret generic operator-oauth \
  --from-literal=client_id=... --from-literal=client_secret=...

kubectl -n mcp-server create secret generic mcp-tokens \
  --from-literal=MCP_TOKEN_CLAUDE=... --from-literal=MCP_TOKEN_GEMINI=...

kubectl -n mcp-server create secret generic mcp-mariadb \
  --from-literal=MARIADB_USER=... --from-literal=MARIADB_PW=...

kubectl -n mcp-server create secret generic mcp-kafka \
  --from-literal=KAFKA_USER=... --from-literal=KAFKA_PW=...
```

No image pull secret is needed: nodes authenticate to Artifact Registry via
containerd (`ansible/Setup_k3s_Registries.yaml`, Reader service account).

## Apply order

Order matters: policies must exist before workloads.

```bash
kubectl apply -f k8s/mcp/00-namespaces.yaml
kubectl apply -f k8s/mcp/10-netpol-mcp-server.yaml -f k8s/mcp/11-netpol-tailscale.yaml
kubectl apply -f k8s/mcp/20-rbac.yaml -f k8s/mcp/30-quota.yaml
kubectl apply -f k8s/mcp/40-nfs-readonly.yaml
# create secrets (above), then:
helm repo add tailscale https://pkgs.tailscale.com/helmcharts && helm repo update
helm upgrade --install tailscale-operator tailscale/tailscale-operator \
  -n tailscale -f k8s/tailscale-operator/values.yaml
kubectl apply -f k8s/mcp/50-mcp-server.yaml
kubectl apply -f k8s/mcp/60-funnel-ingress.yaml
```

Review first with `kubectl diff -f k8s/mcp/<file>` or
`kubectl apply --server-side --dry-run=server -f ...`.

## Verify

```bash
# Policy enforcement: a pod in another namespace must NOT reach the service
kubectl run nettest -n default --rm -it --image=busybox --restart=Never -- \
  wget -T3 -qO- http://mcp-server.mcp-server.svc:8000   # expect timeout

# Live pod spec has the read-only NFS mount and restricted context
kubectl -n mcp-server get pod -l app=mcp-server -o yaml | grep -B2 -A6 datafiles

# RBAC is read-only
kubectl auth can-i --list --as=system:serviceaccount:mcp-server:mcp-server
kubectl auth can-i get secrets --as=system:serviceaccount:mcp-server:mcp-server  # no

# Funnel up
kubectl -n tailscale get pods; kubectl -n mcp-server get ingress mcp-funnel
```

## Known limits

- NFS read-only is enforced client-side only (export is Mapall, writable).
- The operator is privileged; keep it patched and its OAuth client tag-scoped.
- Pods share a node kernel; this is a mitigated, not eliminated, risk.
- Pod logs are deliberately excluded from RBAC; add `pods/log` only on purpose.
