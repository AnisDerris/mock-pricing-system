# Food Delivery — Dynamic Pricing System

Moteur de **dynamic pricing temps réel** pour une plateforme de food delivery (inspiré Uber Eats / DoorDash / Glovo).

---

## Architecture globale

```
[Producers] ──► [Kafka] ──► [Consumers] ──► [Redis] ──► [Pricing API (FastAPI)] ──► [Client SSE]
                                                               │
                                                          [PostgreSQL]
                                                        (persistance / audit)
```

| Couche | Rôle |
|---|---|
| **Producers** | Génèrent des événements synthétiques temps réel |
| **Kafka** | Bus événementiel asynchrone — découplage total |
| **Consumers** | Traitent les événements en parallèle et mettent Redis à jour |
| **Redis** | Miroir de l'état courant — latence < 1 ms |
| **FastAPI** | Calcule le prix dynamique multi-facteurs |
| **PostgreSQL** | Persistance durable + historique + audit pricing |
| **SSE** | Le client reçoit les mises à jour de prix sans rechargement |

---

## Structure du projet

```
MockPricingSystem/
├── app/
│   ├── api/
│   │   ├── config.py        # Configuration 12-factor (env vars)
│   │   ├── schemas.py       # Modèles Pydantic (requête / réponse)
│   │   ├── pricing.py       # Moteur de pricing pur (sans I/O)
│   │   ├── store.py         # Wrapper Redis (lecture/écriture état)
│   │   ├── database.py      # PostgreSQL async (SQLAlchemy + asyncpg)
│   │   ├── weather.py       # Multiplicateur météo (Open-Meteo API)
│   │   └── main.py          # FastAPI — endpoints + SSE + audit
│   └── streaming/
│       ├── producer.py      # Kafka producer (5 types d'événements)
│       └── consumer.py      # Kafka consumer (spécialisé par CONSUMER_TYPE)
├── deploy/
│   ├── docker-compose.yml   # Stack complète locale
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   └── Dockerfile.streaming
│   ├── monitoring/
│   │   ├── prometheus.yml
│   │   ├── loki-config.yml
│   │   ├── promtail-config.yml
│   │   └── grafana/
│   │       ├── provisioning/
│   │       │   ├── datasources/all.yml
│   │       │   └── dashboards/provider.yml
│   │       └── dashboards/food-pricing.json
│   └── k8s/
├── tests/
│   └── test_pricing.py      # Tests mock (aucune dépendance externe)
├── .github/
│   └── workflows/
│       └── dev.yml          # CI/CD GitHub Actions
└── requirements.txt
```

---

## Moteur de pricing — Facteurs dynamiques

Le prix final est calculé via un **multiplicateur composé** de 6 facteurs :

```
surge = demand_mult × driver_availability_mult × restaurant_load_mult
        × traffic_mult × weather_mult × hour_mult

total = (base_fare + distance_cost + prep_time_cost) × surge
```

| Facteur | Description | Impact |
|---|---|---|
| **Demand** | Ratio commandes actives / livreurs disponibles | Demande élevée = prix ↑ |
| **Driver availability** | Nombre absolu de livreurs dans la zone | Peu de livreurs = prix ↑ |
| **Restaurant load** | Taux de charge cuisine (0.0 → 1.0) | Cuisine surchargée = attente ↑ = prix ↑ |
| **Traffic** | Conditions routières par zone (1.0 → 2.0) | Embouteillages = livraison lente = prix ↑ |
| **Weather** | Météo temps réel (Open-Meteo) | Pluie / neige / orage = prix ↑ |
| **Hour** | Heure de pointe (déjeuner 12-14h, dîner 19-22h) | Peak hours = prix ↑ |

> Le surge est **plafonné** à `surge_max = 2.5` pour éviter les prix abusifs.

### Pourquoi le food delivery est différent du VTC

| Paramètre | VTC | Food Delivery |
|---|---|---|
| Point de départ du coût | Départ conducteur | Confirmation commande |
| Préparation restaurant | ❌ | ✅ Intégré au pricing |
| Charge cuisine | ❌ | ✅ Facteur clé |
| Temps de prep | ❌ | ✅ Capturé dans le multiplicateur |
| Zone de diffusion trop petite | ❌ | ✅ Livreur attend = coût caché |

Si un restaurant est surchargé ou si la zone de diffusion est trop restreinte,
le livreur attend au restaurant — c'est un **coût caché** que le pricing capture
via `restaurant_load_multiplier`.

---

## Streaming Kafka — Topics & Consumers

```
[orders-events]      ──► consumer-orders      ──► zone:{zone}:orders
[drivers-events]     ──► consumer-drivers     ──► zone:{zone}:drivers
[restaurants-events] ──► consumer-restaurants ──► restaurant:{id}:load / prep_time / open
[traffic-events]     ──► consumer-traffic     ──► zone:{zone}:traffic
[weather-events]     ──► (Open-Meteo sur chemin critique)
```

Chaque consumer tourne dans son propre container avec `CONSUMER_TYPE` défini —
ils scalent **indépendamment** et ne se bloquent pas mutuellement.

### Clés Redis (TTL courts)

```
zone:{zone}:orders          → commandes actives         (TTL 5 min)
zone:{zone}:drivers         → livreurs disponibles      (TTL 5 min)
zone:{zone}:traffic         → facteur trafic 1.0-2.0    (TTL 2 min)
restaurant:{id}:load        → taux de charge 0.0-1.0    (TTL 3 min)
restaurant:{id}:prep_time   → temps de préparation (min) (TTL 3 min)
restaurant:{id}:open        → statut ouvert/fermé        (TTL 5 min)
```

---

## API — Endpoints

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck |
| `POST` | `/price` | Prix instantané (JSON) |
| `POST` | `/price/stream` | **SSE** — prix mis à jour toutes les 5 s pendant 60 s |
| `GET` | `/zones/{zone}` | État temps réel d'une zone |
| `GET` | `/restaurants/{id}` | État temps réel d'un restaurant |
| `GET` | `/metrics` | Métriques Prometheus |
| `GET` | `/docs` | Swagger UI |

### Exemple requête `POST /price`

```json
{
  "restaurant_id": "mcdo-casa-center",
  "zone_livraison": "casa-center",
  "adresse": "23 Rue Mohammed V, Casablanca",
  "distance_km": 3.5,
  "heure": 12.5,
  "type_commande": "delivery",
  "lat": 33.5731,
  "lon": -7.5898
}
```

### Exemple réponse

```json
{
  "restaurant_id": "mcdo-casa-center",
  "zone_livraison": "casa-center",
  "base_fare": 1.50,
  "distance_cost": 2.63,
  "prep_time_cost": 1.50,
  "demand_multiplier": 1.20,
  "driver_availability_multiplier": 1.15,
  "restaurant_load_multiplier": 1.28,
  "traffic_multiplier": 1.09,
  "weather_multiplier": 1.10,
  "surge_multiplier": 2.17,
  "estimated_prep_minutes": 18.5,
  "estimated_delivery_minutes": 9.2,
  "total": 12.38,
  "currency": "MAD"
}
```

### SSE `POST /price/stream`

Le client reçoit un flux `text/event-stream` avec des événements JSON toutes les 5 secondes.
Utile pour afficher le prix en temps réel côté client sans rechargement de page :

```
data: {"restaurant_id":"mcdo-casa-center","total":12.38,...}

data: {"restaurant_id":"mcdo-casa-center","total":13.10,...}

data: {"stream":"ended"}
```

---

## PostgreSQL — Persistance & Audit

Chaque appel à `/price` génère une entrée dans `pricing_history` de façon
**asynchrone non-bloquante** — la latence de réponse n'est pas impactée.

Les tables sont créées automatiquement au démarrage de l'API.

### Table `pricing_history`

| Colonne | Description |
|---|---|
| `id` | PK auto-increment |
| `created_at` | Horodatage UTC |
| `restaurant_id` | Restaurant concerné |
| `zone_livraison` | Zone de livraison |
| `distance_km` | Distance calculée |
| `heure` | Heure de la commande |
| `type_commande` | `delivery` ou `pickup` |
| `*_multiplier` | Chaque facteur de pricing (6 colonnes) |
| `surge_multiplier` | Multiplicateur final combiné |
| `total` | Prix final calculé |

### Séparation Redis / PostgreSQL

```
Redis       → état courant, TTL court, < 1 ms   → chemin critique (pricing)
PostgreSQL  → historique, durabilité, analytics  → hors chemin critique
```

---

## Monitoring — Grafana + Loki + Prometheus

| Service | Port | Rôle |
|---|---|---|
| **Prometheus** | `9090` | Scrape les métriques `/metrics` de l'API |
| **Loki** | `3100` | Agrège les logs de tous les containers |
| **Promtail** | — | Lit les logs Docker → envoie à Loki |
| **Grafana** | `3000` | Dashboards — login : `admin` / `admin` |

Le dashboard **Food Delivery — Dynamic Pricing** est provisionné automatiquement
au démarrage de Grafana avec :

- Requêtes/sec sur `POST /price` et `POST /price/stream`
- Latences p50 / p95 / p99
- Taux d'erreurs 5xx
- Logs en temps réel de tous les services (Loki)

---

## Démarrage local

### Prérequis

- Docker Desktop ≥ 4.x avec au moins 4 Go de RAM alloués

### Lancer la stack

```bash
git clone <repo>
cd MockPricingSystem/deploy

docker compose up -d --build
```

### Vérifier que tout est up

```bash
docker compose ps
```

### Tester l'API

```bash
# Healthcheck
curl http://localhost:8000/health

# Prix instantané
curl -X POST http://localhost:8000/price \
  -H "Content-Type: application/json" \
  -d '{
        "restaurant_id": "mcdo-casa-center",
        "zone_livraison": "casa-center",
        "adresse": "23 Rue Mohammed V, Casablanca",
        "distance_km": 3.5,
        "heure": 12.5,
        "type_commande": "delivery",
        "lat": 33.5731,
        "lon": -7.5898
      }'

# État d'une zone
curl http://localhost:8000/zones/casa-center

# État d'un restaurant
curl http://localhost:8000/restaurants/mcdo-casa-center
```

### URLs des services

| Service | URL |
|---|---|
| API Swagger | http://localhost:8000/docs |
| API métriques | http://localhost:8000/metrics |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

### Arrêter

```bash
docker compose down
# Supprimer aussi les volumes persistants :
docker compose down -v
```

---

## CI/CD — GitHub Actions

Le workflow `.github/workflows/dev.yml` se déclenche sur chaque push vers `dev` :

```
push → dev
  │
  ├── [Job 1] Mock Tests (ubuntu-latest)
  │     ├── pip install -r requirements.txt
  │     └── pytest tests/ -v --tb=short
  │
  └── [Job 2] Deploy (uniquement si les tests passent)
        └── SSH → serveur distant
              ├── git pull origin dev
              ├── docker compose up -d --build --remove-orphans
              └── docker image prune -f
```

### Secrets GitHub à configurer

| Secret | Description |
|---|---|
| `REMOTE_HOST` | IP ou hostname du serveur cible |
| `REMOTE_USER` | Utilisateur SSH |
| `SSH_PRIVATE_KEY` | Clé SSH privée (Ed25519 recommandé) |
| `REMOTE_PATH` | Chemin absolu du projet sur le serveur |
| `REMOTE_PORT` | Port SSH (optionnel, défaut : 22) |

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `BASE_FARE` | `1.50` | Tarif de base (MAD) |
| `PER_KM` | `0.75` | Tarif par km |
| `PER_MIN_PREP` | `0.10` | Tarif par minute de préparation |
| `SURGE_MAX` | `2.5` | Plafond du multiplicateur |
| `REDIS_URL` | `redis://redis:6379/0` | URL Redis |
| `DATABASE_URL` | `postgresql+asyncpg://pricing:pricing@postgres:5432/foodpricing` | URL PostgreSQL async |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Broker Kafka |
| `CONSUMER_TYPE` | `orders` | Type du consumer (`orders\|drivers\|restaurants\|traffic`) |
| `PRODUCER_INTERVAL` | `0.8` | Intervalle entre événements produits (secondes) |
| `LOG_LEVEL` | `INFO` | Niveau de log |

---

## Tests

Les tests sont **100 % unitaires** — aucune dépendance externe (pas de Redis, Kafka ou PostgreSQL requis).
Ils s'exécutent en isolation complète dans le pipeline CI.

```bash
pytest tests/ -v
```

| Test | Ce qui est vérifié |
|---|---|
| `test_demand_*` | Équilibre, rareté des livreurs, saturation, zone idle |
| `test_driver_availability_*` | 4 paliers de disponibilité |
| `test_restaurant_load_*` | Idle → full + clamping haut et bas |
| `test_traffic_*` | Route fluide → embouteillages + clamping |
| `test_hour_*` | Heures de pointe déjeuner / dîner / nuit / normal |
| `test_quote_*` | Décomposition des coûts, plafonnement surge, temps estimés |


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
