# Mock Pricing System

A demo dynamic pricing platform inspired by Uber/Lyft surge pricing — built for the
DevOps internship project (tasks **DEVOPS-104** & **DEVOPS-105**).

It is intentionally small and readable: the goal is to **practice deployment**
(Docker, Kubernetes, Helm, CI/CD), not to ship a real pricing engine.

---

## 1. What it does

```
┌──────────────┐     ┌────────────┐     ┌──────────────┐     ┌──────────────┐
│  Producer    │ ──► │  RabbitMQ  │ ──► │  Consumer    │ ──► │   Redis      │
│ (signals:    │     │  (signals) │     │  (updates    │     │ (live demand │
│  rides,      │     └────────────┘     │   demand)    │     │  per zone)   │
│  drivers)    │                        └──────────────┘     └──────┬───────┘
└──────────────┘                                                    │
                                                                    ▼
                                                            ┌──────────────┐
                                  HTTP /price ─────────────►│ Pricing API  │
                                                            │  (FastAPI)   │
                                                            └──────┬───────┘
                                                                   │
                                                  Open-Meteo (free)│
                                                                   ▼
                                                            weather multiplier
```

**Pricing formula** (Uber/Lyft inspired):

```
fare = base_fare
     + (distance_km   * per_km)
     + (duration_min  * per_min)

surge = demand_multiplier(zone) * weather_multiplier(zone)
total = round(fare * clamp(surge, 1.0, 3.0), 2)
```

- `demand_multiplier` is computed from live rides/drivers ratio in Redis.
- `weather_multiplier` calls the **free** [Open-Meteo](https://open-meteo.com)
  API (no API key, no signup) — rain/snow bumps the surge.

---

## 2. Repository layout

```
.
├── app/
│   ├── api/                 # FastAPI pricing service (DEVOPS-104)
│   │   ├── main.py
│   │   ├── pricing.py
│   │   ├── weather.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   └── store.py
│   └── streaming/           # Producer & consumer (DEVOPS-105)
│       ├── producer.py
│       └── consumer.py
├── tests/
│   └── test_pricing.py
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   └── Dockerfile.streaming
│   ├── docker-compose.yml
│   └── k8s/
│       ├── namespace.yaml
│       ├── redis.yaml
│       ├── rabbitmq.yaml
│       ├── api.yaml
│       ├── consumer.yaml
│       └── producer.yaml
├── requirements.txt
└── README.md
```

---

## 3. Run locally with Docker Compose

```bash
cd deploy
docker compose up --build
```

Then:

```bash
# Health
curl http://localhost:8000/health

# Get a price quote (Casablanca center → airport)
curl -X POST http://localhost:8000/price \
  -H "Content-Type: application/json" \
  -d '{
        "zone": "casa-center",
        "distance_km": 12.5,
        "duration_min": 22,
        "lat": 33.5731,
        "lon": -7.5898
      }'

# See live surge state for a zone
curl http://localhost:8000/zones/casa-center
```

The producer container automatically emits ride/driver signals every second so
you can watch `surge` move up and down.

RabbitMQ UI: http://localhost:15672 (guest / guest)

---

## 4. Run tests

```bash
pip install -r requirements.txt
pytest -q
```

---

## 5. Deploy to Kubernetes

Assumes a working cluster (`minikube`, `kind`, or cloud) and `kubectl`
context already set.

```bash
# 1. Build & push images (replace <REGISTRY>)
docker build -f deploy/docker/Dockerfile.api       -t <REGISTRY>/mock-pricing-api:0.1.0 .
docker build -f deploy/docker/Dockerfile.streaming -t <REGISTRY>/mock-pricing-stream:0.1.0 .
docker push <REGISTRY>/mock-pricing-api:0.1.0
docker push <REGISTRY>/mock-pricing-stream:0.1.0

# 2. Update image refs in deploy/k8s/*.yaml (search for <REGISTRY>)

# 3. Apply manifests
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/

# 4. Port-forward and try it
kubectl -n pricing port-forward svc/pricing-api 8000:8000
curl http://localhost:8000/health
```

Resources created (namespace `pricing`):

| Kind        | Name             | Purpose                          |
| ----------- | ---------------- | -------------------------------- |
| Deployment  | `pricing-api`    | FastAPI pricing service (2 reps) |
| Deployment  | `signal-consumer`| Reads RabbitMQ → Redis           |
| Deployment  | `signal-producer`| Generates fake signals           |
| StatefulSet | `redis`          | Demand state                     |
| StatefulSet | `rabbitmq`       | Message broker                   |
| Service     | `pricing-api`    | ClusterIP :8000                  |

Liveness/readiness probes hit `/health`. Both Deployments expose Prometheus
metrics on `/metrics` (via `prometheus-fastapi-instrumentator`).

---

## 6. Endpoints

| Method | Path             | Description                              |
| ------ | ---------------- | ---------------------------------------- |
| GET    | `/health`        | Liveness + readiness                     |
| GET    | `/metrics`       | Prometheus metrics                       |
| POST   | `/price`         | Quote a ride                             |
| GET    | `/zones/{zone}`  | Current demand & surge state for a zone  |

---

## 7. Design notes

- **12-factor:** all config via env vars (`app/api/config.py`).
- **Stateless API:** scaling is trivial — state lives in Redis & RabbitMQ.
- **Fail-open weather:** if Open-Meteo is down, `weather_multiplier = 1.0`
  and we keep serving prices.
- **Bounded surge:** clamped to `[1.0, 3.0]` to avoid runaway multipliers.
- **Dead-letter queue:** invalid messages go to `signals.dlq` instead of
  blocking the consumer.
