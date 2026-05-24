"""Event producers food delivery — Orders, Drivers, Restaurants, Traffic, Weather.

Génère des événements synthétiques sur 5 topics Kafka pour alimenter
le moteur de pricing en temps réel.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

LOG = logging.getLogger("producer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
INTERVAL = float(os.getenv("PRODUCER_INTERVAL", "1.0"))

ZONES = ["casa-center", "rabat-agdal", "marrakech-medina", "agadir-talborjt"]
RESTAURANTS = [
    "mcdo-casa-center",
    "pizza-hut-agdal",
    "sushi-king-medina",
    "burger-house-casa",
    "le-petit-chef-agadir",
]

TOPICS = {
    "orders": "orders-events",
    "drivers": "drivers-events",
    "restaurants": "restaurants-events",
    "traffic": "traffic-events",
    "weather": "weather-events",
}


def make_producer() -> KafkaProducer:
    while True:
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode(),
                acks="all",
                retries=3,
            )
        except NoBrokersAvailable:
            LOG.warning("Kafka not ready, retrying in 3s…")
            time.sleep(3)


def gen_order_event() -> tuple[str, dict]:
    return TOPICS["orders"], {
        "event": random.choice(["new_order", "cancel_order"]),
        "zone": random.choice(ZONES),
        "restaurant_id": random.choice(RESTAURANTS),
        "delta": 1 if random.random() > 0.2 else -1,
        "ts": time.time(),
    }


def gen_driver_event() -> tuple[str, dict]:
    return TOPICS["drivers"], {
        "event": random.choice(["driver_available", "driver_busy", "driver_offline"]),
        "zone": random.choice(ZONES),
        "delta": random.choice([1, -1]),
        "ts": time.time(),
    }


def gen_restaurant_event() -> tuple[str, dict]:
    return TOPICS["restaurants"], {
        "event": "restaurant_update",
        "restaurant_id": random.choice(RESTAURANTS),
        "load_factor": round(random.uniform(0.0, 1.0), 2),
        "prep_time_minutes": round(random.uniform(8.0, 40.0), 1),
        "is_open": random.random() > 0.05,  # 95 % ouvert
        "ts": time.time(),
    }


def gen_traffic_event() -> tuple[str, dict]:
    return TOPICS["traffic"], {
        "event": "traffic_update",
        "zone": random.choice(ZONES),
        "traffic_factor": round(random.uniform(1.0, 2.0), 2),
        "ts": time.time(),
    }


def gen_weather_event() -> tuple[str, dict]:
    return TOPICS["weather"], {
        "event": "weather_update",
        "zone": random.choice(ZONES),
        "precipitation_mm": round(random.uniform(0, 10), 1),
        "weather_code": random.choices([0, 61, 71, 95], weights=[70, 15, 10, 5])[0],
        "ts": time.time(),
    }


_GENERATORS = [
    (gen_order_event, 0.35),
    (gen_driver_event, 0.25),
    (gen_restaurant_event, 0.20),
    (gen_traffic_event, 0.10),
    (gen_weather_event, 0.10),
]


def main() -> None:
    producer = make_producer()
    LOG.info("Kafka producer ready — interval=%.2fs", INTERVAL)
    generators, weights = zip(*_GENERATORS)
    try:
        while True:
            gen_fn = random.choices(generators, weights=weights)[0]
            topic, payload = gen_fn()
            producer.send(topic, payload)
            LOG.debug("→ %s: %s", topic, payload)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        LOG.info("producer shutting down")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
