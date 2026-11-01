"""Entrypoint: FastMCP (streamable HTTP, stateless) behind bearer-token auth."""
import logging
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import tools_k8s, tools_kafka, tools_mariadb, tools_nfs
from .auth import BearerAuth, load_tokens


def build_app(tokens: dict[str, str] | None = None):
    mcp = FastMCP(
        "datahub-readonly",
        instructions="Read-only access to the my-datahub lab: Kubernetes, MariaDB, Kafka, NFS.",
        host="0.0.0.0",
        port=8000,
        stateless_http=True,
        json_response=True,
        # Reached through a Tailscale Funnel hostname; bearer auth is the control here.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for module in (tools_k8s, tools_mariadb, tools_kafka, tools_nfs):
        module.register(mcp)
    return BearerAuth(mcp.streamable_http_app(), tokens or load_tokens())


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(build_app(), host="0.0.0.0", port=8000, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="*")
