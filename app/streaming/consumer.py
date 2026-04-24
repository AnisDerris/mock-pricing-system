"""Signal consumer: validates messages and updates demand counters in Redis.

Bad messages are routed to a dead-letter queue (`signals.dlq`) instead of
blocking the main flow.
"""
from __future__ import annotations

import json
import logging
import os
import time

import pika
import redis

LOG = logging.getLogger("consumer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EXCHANGE = os.getenv("SIGNAL_EXCHANGE", "signals")
QUEUE = os.getenv("SIGNAL_QUEUE", "signals.main")
DLQ = os.getenv("SIGNAL_DLQ", "signals.dlq")
TTL_SECONDS = int(os.getenv("DEMAND_TTL_SECONDS", "300"))

VALID_KINDS = {"ride", "driver"}
KIND_TO_KEY = {"ride": "rides", "driver": "drivers"}


def setup(ch: pika.adapters.blocking_connection.BlockingChannel) -> None:
    ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    ch.queue_declare(queue=DLQ, durable=True)
    ch.queue_declare(
        queue=QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": DLQ},
    )
    ch.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key="signal.*")


def handle(rds: redis.Redis, body: bytes) -> None:
    msg = json.loads(body)
    zone = msg["zone"]
    kind = msg["kind"]
    delta = int(msg.get("delta", 1))
    if kind not in VALID_KINDS or not isinstance(zone, str) or not zone:
        raise ValueError(f"invalid signal: {msg}")

    key = f"zone:{zone}:{KIND_TO_KEY[kind]}"
    pipe = rds.pipeline()
    pipe.incrby(key, delta)
    pipe.expire(key, TTL_SECONDS)
    new_val, _ = pipe.execute()
    if int(new_val) < 0:  # never let counters go negative
        rds.set(key, 0, ex=TTL_SECONDS)


def run() -> None:
    rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    while True:
        try:
            conn = pika.BlockingConnection(pika.URLParameters(RABBIT_URL))
            ch = conn.channel()
            setup(ch)
            ch.basic_qos(prefetch_count=32)
            LOG.info("consumer ready on queue=%s", QUEUE)

            def on_msg(channel, method, _props, body):
                try:
                    handle(rds, body)
                    channel.basic_ack(method.delivery_tag)
                except Exception as exc:
                    LOG.error("bad message -> DLQ: %s", exc)
                    channel.basic_nack(method.delivery_tag, requeue=False)

            ch.basic_consume(queue=QUEUE, on_message_callback=on_msg)
            ch.start_consuming()
        except pika.exceptions.AMQPConnectionError as exc:
            LOG.warning("rabbit connection lost (%s), retrying in 3s", exc)
            time.sleep(3)


if __name__ == "__main__":
    run()
