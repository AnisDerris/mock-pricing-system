"""Synthetic signal producer: emits ride requests and driver availability.

Keeps the demo lively so surge multipliers visibly change over time.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time

import pika

LOG = logging.getLogger("producer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE = os.getenv("SIGNAL_EXCHANGE", "signals")
ZONES = ["casa-center", "rabat-agdal", "marrakech-medina"]
INTERVAL_SECONDS = float(os.getenv("PRODUCER_INTERVAL", "1.0"))


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(RABBIT_URL)
    params.heartbeat = 30
    return pika.BlockingConnection(params)


def main() -> None:
    while True:
        try:
            conn = connect()
            ch = conn.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            LOG.info("producer connected, publishing every %.2fs", INTERVAL_SECONDS)

            while True:
                kind = random.choices(["ride", "driver"], weights=[0.6, 0.4])[0]
                payload = {
                    "zone": random.choice(ZONES),
                    "kind": kind,
                    "delta": 1 if random.random() > 0.15 else -1,
                    "ts": time.time(),
                }
                ch.basic_publish(
                    exchange=EXCHANGE,
                    routing_key=f"signal.{kind}",
                    body=json.dumps(payload).encode(),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                LOG.debug("sent %s", payload)
                time.sleep(INTERVAL_SECONDS)
        except pika.exceptions.AMQPConnectionError as exc:
            LOG.warning("rabbit connection lost (%s), retrying in 3s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
