"""Kafka read-only tools: topic metadata and bounded message reads.

Uses assign() with no commits, so it never joins or disturbs a consumer group.
"""
import os
import uuid

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient

from .common import audited, jsonable

MAX_MESSAGES = 50
MAX_VALUE_BYTES = 2000


def _conf() -> dict:
    return {
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
        "security.protocol": os.environ.get("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT"),
        "sasl.mechanisms": os.environ.get("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"),
        "sasl.username": os.environ["KAFKA_USER"],
        "sasl.password": os.environ["KAFKA_PW"],
    }


def _decode(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    text = raw[:MAX_VALUE_BYTES].decode("utf-8", errors="replace")
    return text + ("...[truncated]" if len(raw) > MAX_VALUE_BYTES else "")


def register(mcp):
    @mcp.tool()
    @audited
    def kafka_list_topics(include_internal: bool = False) -> dict:
        """List topics with partition counts."""
        md = AdminClient(_conf()).list_topics(timeout=10)
        topics = [
            {"topic": name, "partitions": len(t.partitions)}
            for name, t in sorted(md.topics.items())
            if include_internal or not name.startswith("__")
        ]
        return {"count": len(topics), "topics": topics}

    @mcp.tool()
    @audited
    def kafka_describe_topic(topic: str) -> dict:
        """Partition leaders/replicas/ISR plus low/high offsets (message counts)."""
        consumer = Consumer({**_conf(), "group.id": f"mcp-readonly-{uuid.uuid4().hex[:8]}",
                             "enable.auto.commit": False})
        try:
            md = consumer.list_topics(topic, timeout=10)
            tmeta = md.topics.get(topic)
            if tmeta is None or tmeta.error is not None:
                raise ValueError(f"topic {topic!r} not found")
            parts = []
            for pid, p in sorted(tmeta.partitions.items()):
                low, high = consumer.get_watermark_offsets(TopicPartition(topic, pid), timeout=10)
                parts.append({"partition": pid, "leader": p.leader, "replicas": list(p.replicas),
                              "isr": list(p.isrs), "low": low, "high": high})
            return jsonable({"topic": topic, "partitions": parts})
        finally:
            consumer.close()

    @mcp.tool()
    @audited
    def kafka_read_messages(topic: str, partition: int = 0, limit: int = 10,
                            from_end: bool = True, start_offset: int | None = None) -> dict:
        """Read up to `limit` (max 50) messages from one partition: the latest by default,
        or from start_offset. Values truncated to 2000 bytes. Never commits offsets."""
        limit = max(1, min(limit, MAX_MESSAGES))
        consumer = Consumer({**_conf(), "group.id": f"mcp-readonly-{uuid.uuid4().hex[:8]}",
                             "enable.auto.commit": False, "enable.partition.eof": False})
        try:
            low, high = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=10)
            if start_offset is not None:
                start = max(low, min(start_offset, high))
            elif from_end:
                start = max(low, high - limit)
            else:
                start = low
            consumer.assign([TopicPartition(topic, partition, start)])
            out = []
            misses = 0
            while len(out) < limit and misses < 3:
                msg = consumer.poll(2.0)
                if msg is None:
                    misses += 1
                    continue
                if msg.error():
                    raise RuntimeError(str(msg.error()))
                out.append({"offset": msg.offset(), "timestamp": msg.timestamp()[1],
                            "key": _decode(msg.key()), "value": _decode(msg.value())})
            return jsonable({"topic": topic, "partition": partition, "low": low, "high": high,
                             "messages": out})
        finally:
            consumer.close()
