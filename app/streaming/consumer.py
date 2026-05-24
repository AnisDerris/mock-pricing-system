"""Kafka consumers food delivery — traitement parallèle, Redis-backed.

Chaque instance est spécialisée via la variable d'env CONSUMER_TYPE :
  orders | drivers | restaurants | traffic

Chaque consumer met à jour sa clé Redis dédiée → miroir temps réel.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

import redis
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

LOG = logging.getLogger("consumer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_TYPE = os.getenv("CONSUMER_TYPE", "orders")  # orders|drivers|restaurants|traffic
TTL = int(os.getenv("DEMAND_TTL_SECONDS", "300"))

TOPIC_MAP = {
    "orders": "orders-events",
    "drivers": "drivers-events",
    "restaurants": "restaurants-events",
    "traffic": "traffic-events",
}


def make_consumer(consumer_type: str) -> KafkaConsumer:
    topic = TOPIC_MAP[consumer_type]
    while True:
        try:
            return KafkaConsumer(
                topic,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=f"food-pricing-{consumer_type}",
                value_deserializer=lambda b: json.loads(b),
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
        except NoBrokersAvailable:
            LOG.warning("Kafka not ready, retrying in 3s…")
            time.sleep(3)


# ── Handlers ────────────────────────────────────────────────────────────────

def handle_order(rds: redis.Redis, msg: dict) -> None:
    zone = msg["zone"]
    delta = int(msg.get("delta", 1))
    key = f"zone:{zone}:orders"
    pipe = rds.pipeline()
    pipe.incrby(key, delta)
    pipe.expire(key, TTL)
    val, _ = pipe.execute()
    if int(val) < 0:
        rds.set(key, 0, ex=TTL)
    LOG.debug("orders zone=%s delta=%d", zone, delta)


def handle_driver(rds: redis.Redis, msg: dict) -> None:
    zone = msg["zone"]
    delta = int(msg.get("delta", 1))
    key = f"zone:{zone}:drivers"
    pipe = rds.pipeline()
    pipe.incrby(key, delta)
    pipe.expire(key, TTL)
    val, _ = pipe.execute()
    if int(val) < 0:
        rds.set(key, 0, ex=TTL)
    LOG.debug("drivers zone=%s delta=%d", zone, delta)


def handle_restaurant(rds: redis.Redis, msg: dict) -> None:
    rid = msg["restaurant_id"]
    load = float(msg.get("load_factor", 0.3))
    prep = float(msg.get("prep_time_minutes", 15.0))
    is_open = bool(msg.get("is_open", True))
    rds.set(f"restaurant:{rid}:load", round(load, 3), ex=180)
    rds.set(f"restaurant:{rid}:prep_time", round(prep, 1), ex=180)
    rds.set(f"restaurant:{rid}:open", "1" if is_open else "0", ex=300)
    LOG.debug("restaurant id=%s load=%.2f prep=%.1f", rid, load, prep)


def handle_traffic(rds: redis.Redis, msg: dict) -> None:
    zone = msg["zone"]
    factor = float(msg.get("traffic_factor", 1.0))
    rds.set(f"zone:{zone}:traffic", round(factor, 3), ex=120)
    LOG.debug("traffic zone=%s factor=%.2f", zone, factor)


HANDLERS = {
    "orders": handle_order,
    "drivers": handle_driver,
    "restaurants": handle_restaurant,
    "traffic": handle_traffic,
}


def run(consumer_type: str) -> None:
    if consumer_type not in HANDLERS:
        LOG.error(
            "Unknown consumer type: %s. Choose from: %s",
            consumer_type,
            list(HANDLERS),
        )
        sys.exit(1)

    rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    handler = HANDLERS[consumer_type]
    consumer = make_consumer(consumer_type)
    LOG.info(
        "consumer[%s] ready on topic=%s", consumer_type, TOPIC_MAP[consumer_type]
    )

    try:
        for message in consumer:
            try:
                handler(rds, message.value)
            except Exception as exc:
                LOG.error("failed to handle message: %s — %s", message.value, exc)
    except KeyboardInterrupt:
        LOG.info("consumer[%s] shutting down", consumer_type)
    finally:
        consumer.close()


if __name__ == "__main__":
    run(CONSUMER_TYPE)
