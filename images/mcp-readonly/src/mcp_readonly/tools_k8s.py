"""Kubernetes read-only tools (get/list/watch via the pod's service account)."""
import threading

from kubernetes import client, config

from .common import audited, jsonable

# kind -> (api group key, singular method fragment)
NAMESPACED = {
    "pods": ("core", "pod"),
    "services": ("core", "service"),
    "endpoints": ("core", "endpoints"),
    "persistentvolumeclaims": ("core", "persistent_volume_claim"),
    "events": ("core", "event"),
    "deployments": ("apps", "deployment"),
    "statefulsets": ("apps", "stateful_set"),
    "daemonsets": ("apps", "daemon_set"),
    "replicasets": ("apps", "replica_set"),
    "jobs": ("batch", "job"),
    "cronjobs": ("batch", "cron_job"),
    "ingresses": ("net", "ingress"),
    "networkpolicies": ("net", "network_policy"),
}
CLUSTER = {
    "nodes": ("core", "node"),
    "namespaces": ("core", "namespace"),
    "persistentvolumes": ("core", "persistent_volume"),
}
KINDS = sorted(NAMESPACED) + sorted(CLUSTER)

_apis: dict = {}
_lock = threading.Lock()


def _api(group: str):
    with _lock:
        if not _apis:
            config.load_incluster_config()
            _apis.update(
                core=client.CoreV1Api(),
                apps=client.AppsV1Api(),
                batch=client.BatchV1Api(),
                net=client.NetworkingV1Api(),
                custom=client.CustomObjectsApi(),
            )
        return _apis[group]


def redact(obj):
    """Drop managedFields and literal env values (they may hold secrets)."""
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if key == "managedFields":
                continue
            if key == "env" and isinstance(val, list):
                out[key] = [
                    {**e, "value": "<redacted>"} if isinstance(e, dict) and "value" in e else e
                    for e in val
                ]
            else:
                out[key] = redact(val)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def _check_kind(kind: str):
    if kind not in NAMESPACED and kind not in CLUSTER:
        raise ValueError(f"unsupported kind {kind!r}; choose from {KINDS}")


def _summary(item: dict) -> dict:
    meta = item.get("metadata", {})
    return {
        "name": meta.get("name"),
        "namespace": meta.get("namespace"),
        "created": meta.get("creationTimestamp"),
        "labels": meta.get("labels"),
        "status": item.get("status"),
    }


def register(mcp):
    @mcp.tool()
    @audited
    def k8s_list(kind: str, namespace: str | None = None, label_selector: str | None = None,
                 limit: int = 200) -> dict:
        """List Kubernetes objects (summary view). kind is one of the supported kinds
        (pods, nodes, deployments, services, events, ...). Omit namespace for all."""
        _check_kind(kind)
        limit = max(1, min(limit, 500))
        kw = {"limit": limit}
        if label_selector:
            kw["label_selector"] = label_selector
        if kind in CLUSTER:
            group, single = CLUSTER[kind]
            res = getattr(_api(group), f"list_{single}")(**kw)
        else:
            group, single = NAMESPACED[kind]
            if namespace:
                res = getattr(_api(group), f"list_namespaced_{single}")(namespace, **kw)
            else:
                res = getattr(_api(group), f"list_{single}_for_all_namespaces")(**kw)
        items = client.ApiClient().sanitize_for_serialization(res)["items"]
        return jsonable({"count": len(items), "items": [_summary(redact(i)) for i in items]})

    @mcp.tool()
    @audited
    def k8s_get(kind: str, name: str, namespace: str | None = None) -> dict:
        """Get one Kubernetes object in full (secrets never exposed; env values redacted)."""
        _check_kind(kind)
        if kind in CLUSTER:
            group, single = CLUSTER[kind]
            obj = getattr(_api(group), f"read_{single}")(name)
        else:
            if not namespace:
                raise ValueError("namespace is required for namespaced kinds")
            group, single = NAMESPACED[kind]
            obj = getattr(_api(group), f"read_namespaced_{single}")(name, namespace)
        return jsonable(redact(client.ApiClient().sanitize_for_serialization(obj)))

    @mcp.tool()
    @audited
    def k8s_top(kind: str = "nodes", namespace: str | None = None) -> dict:
        """CPU/memory usage from metrics-server. kind is 'nodes' or 'pods'."""
        if kind not in ("nodes", "pods"):
            raise ValueError("kind must be 'nodes' or 'pods'")
        custom = _api("custom")
        if kind == "pods" and namespace:
            res = custom.list_namespaced_custom_object("metrics.k8s.io", "v1beta1", namespace, "pods")
        else:
            res = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", kind)
        return jsonable({
            "items": [
                {"name": i["metadata"]["name"], "namespace": i["metadata"].get("namespace"),
                 "usage": i.get("usage") or i.get("containers")}
                for i in res["items"]
            ]
        })
