"""Shared helpers: per-request client identity and tool-call audit logging."""
import contextvars
import functools
import json
import logging

import anyio

log = logging.getLogger("mcp_readonly.audit")

# Set by the bearer-auth middleware so tool calls can be attributed to a client.
client_var: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_client", default="-")


def audited(fn):
    """Log every tool call (client, tool, arguments) and run the sync body in a thread."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        log.info(
            "tool=%s client=%s args=%s",
            fn.__name__,
            client_var.get(),
            json.dumps(kwargs, default=str)[:500],
        )
        try:
            return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
        except Exception as exc:
            log.warning("tool=%s client=%s error=%s", fn.__name__, client_var.get(), exc)
            raise

    return wrapper


def jsonable(obj):
    """Round-trip through JSON so Decimals, datetimes and bytes become plain values."""
    return json.loads(json.dumps(obj, default=str))
