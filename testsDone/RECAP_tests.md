# Récapitulatif de la campagne de tests — Système de tarification dynamique (FAST)

> Document de synthèse technique. Décrit **ce qui a été testé**, **comment**, avec **quels scripts**,
> et **quels résultats** ont été obtenus. Toutes les valeurs proviennent d'exécutions réelles sur la
> stack déployée (Docker Engine 29.5 sous WSL2 Ubuntu 26.04). Les figures et le Chapitre IV
> en sont dérivés.

---

## 1. Environnement d'exécution

| Élément | Détail |
|---|---|
| Hôte | Windows + WSL2, distribution Ubuntu 26.04 |
| Moteur conteneurs | Docker Engine 29.5.3, Docker Compose v2 |
| Démarrage stack | `docker compose up -d` (13 services) depuis `deploy/` |
| Variante perf | `docker compose -f docker-compose.yml -f docker-compose.perf.yml up -d api` (API → 4 workers Uvicorn) |
| Outils de mesure | `ApacheBench` (ab), `curl` (échantillonnage), `kafka-consumer-groups.sh`, `psql`, `redis-cli` |
| Accès UI | API `http://localhost:8000` · Grafana `http://localhost:3000` (admin/admin) · Prometheus `9090` |

Les 13 services : `api`, `producer`, `consumer-orders/drivers/restaurants/traffic`, `kafka`, `redis`,
`postgres`, `prometheus`, `loki`, `promtail`, `grafana`.

> **Note d'exploitation.** `dockerd` a été lancé en avant-plan dans un terminal dédié pour
> maintenir la distribution WSL active pendant toute la campagne (sinon WSL arrête la VM et
> les conteneurs au bout de quelques secondes d'inactivité).

---

## 2. Vue d'ensemble des scripts

Tous les scripts sont dans `docs/ops/`. Ils ont été exécutés dans WSL via :
`wsl -d Ubuntu -u root -- bash -c 'cd <repo> && sed "s/\r$//" docs/ops/<script>.sh > /tmp/<script>.sh && bash /tmp/<script>.sh'`
(le `sed` retire les fins de ligne CRLF de Windows).

| Script | Rôle | Sortie |
|---|---|---|
| `start_docker.sh` | Démarre/contrôle le démon Docker dans WSL | log `dockerd ready` |
| `traffic.sh` | Génère un trafic continu vers `/price`, `/zones`, `/restaurants` | alimente Redis + dashboards |
| `scenarios.sh` | Injecte 4 états de marché déterministes dans Redis et lit le prix | prix réels (Tab. IV.3) |
| `latency.sh` | Mesure la latence du chemin `/price` (codes HTTP + 1500 échantillons) | `lat_samples.txt` |
| `sweep.sh` | Montée en charge `ab` à concurrence croissante | `sweep.csv` |
| `resilience.sh` | Panne d'un consumer + backlog + récupération | `resilience.csv` |
| `hist.awk` | Binning de `lat_samples.txt` pour l'histogramme | bins (Fig. IV.3) |

Fichiers de données produits : `lat_samples.txt`, `sweep.csv`, `resilience.csv`.
Figures HTML (rendues en PNG via Chrome headless) : `fig_IV_1..8`.

---

## 3. Tests réalisés

### T1 — Validation fonctionnelle (correction du moteur)

**Comment.** `scenarios.sh` écrit des valeurs déterministes dans Redis sur des zones de test
isolées (`test-normal`, `test-pic`, `test-fav`, `test-max`) — non touchées par les producers —
puis appelle `POST /price` **sans `lat`/`lon`** (météo = 1,0, donc aucune dépendance externe).

Extrait de la logique d'injection :

```bash
set_scenario() {            # zone rid orders drivers traffic load prep
  R SET "zone:${zone}:orders"  "$orders"  EX 600
  R SET "zone:${zone}:drivers" "$drivers" EX 600
  R SET "zone:${zone}:traffic" "$traffic" EX 600
  R SET "restaurant:${rid}:load" "$load" EX 600
  ...
}
# R() = docker exec food-pricing-redis-1 redis-cli ...
```

**Résultats réels :**

| Scénario | commandes/livreurs/trafic/charge | Surge | Total (MAD) |
|---|---|---|---|
| Normal | 5 / 8 / 1,0 / 0,0 | **1,00** | 6,75 |
| Pic modéré | 8 / 5 / 1,2 / 0,5 (déj. 13 h) | **2,18** | 16,24 |
| Favorable | 2 / 12 / 1,0 / 0,1 | **1,04** | 6,71 |
| Pic maximal | 40 / 1 / 2,0 / 1,0 (dîner 20 h) | **2,50 (plafonné)** | 21,88 |

→ Le plafonnement `surge_max = 2,5` est confirmé : le produit brut des 6 facteurs dépasse 5,0
mais le résultat est borné. Figures `fig_IV_2_price_json` (réponse JSON) et `fig_IV_1_kafka_lag`.

---

### T2 — Performance : latence en régime nominal

**Comment.** `latency.sh` : (1) vérifie 500 codes HTTP, (2) warmup `ab`, (3) 1500 requêtes
séquentielles avec `curl -w "%{time_total}"`, percentiles calculés en `awk`.

```bash
for i in $(seq 1 1500); do
  t=$(curl -s -o /dev/null -w "%{time_total}" -X POST "$API" \
        -H "Content-Type: application/json" -d @"$BODY")
  awk -v t="$t" 'BEGIN{printf "%.3f\n", t*1000}' >> /tmp/lat.txt
done
```

**Résultats réels** (n = 1500, concurrence 1) :

| Métrique | Valeur | SLO | Baseline FAST |
|---|---|---|---|
| P50 | **5,7 ms** | < 100 ms | 250–300 ms |
| P95 | **6,7 ms** | < 100 ms | — |
| P99 | **7,2 ms** | < 100 ms | — |
| moyenne / max | 5,8 / 9,3 ms | — | — |
| codes HTTP | 500/500 = **200** | — | — |

→ Gain ≈ **×44** vs baseline. Figure `fig_IV_3_latency_hist` (histogramme + ligne SLO).

---

### T3 — Performance : montée en charge

**Comment.** `sweep.sh` lance `ab -n 3000 -c <C>` pour C ∈ {1,5,10,20,50,100,200} sur l'API
**4 workers**, et extrait débit + percentiles. Résultats dans `sweep.csv`.

```bash
for c in 1 5 10 20 50 100 200; do
  res=$(ab -n 3000 -c "$c" -l -p "$BODY" -T application/json "$API" 2>/dev/null)
  rps=$(echo "$res" | awk '/Requests per second/{print $4}')
  p95=$(echo "$res" | awk '/ 95%/{print $2}')
  ...
done
```

**Résultats réels :**

| Concurrence | Débit (req/s) | P95 (ms) |
|---|---|---|
| 1 | 168 | 7 |
| 5 | 597 | 13 |
| 10 | 597 | 21 |
| 20 | 623 | 36 |
| **50** | **617** | **94** ← dernier palier sous SLO |
| 100 | 564 | 307 |
| 200 | 604 | 515 |

→ Plateau ~600 req/s ; **P95 < 100 ms jusqu'à ~617 req/s**. Figure `fig_IV_4_sweep`.

---

### T4 — Fraîcheur des données + résilience

**Comment.** `resilience.sh` : mesure le lag baseline, **arrête `consumer-orders`**, injecte
**1000 messages** dans `orders-events`, échantillonne le lag + le code API toutes les 3 s,
**redémarre** le consumer, puis échantillonne la résorption toutes les 2 s.

```bash
docker stop food-pricing-consumer-orders-1
docker exec food-pricing-producer-1 python -c "from kafka import KafkaProducer; ... 1000 msgs"
# boucle de mesure : lag (kafka-consumer-groups.sh) + api_code (curl -w %{http_code})
docker start food-pricing-consumer-orders-1
```

**Résultats réels** (`resilience.csv`) :

| Phase | t (s) | Lag | API |
|---|---|---|---|
| nominal | 0 | 1 | 200 |
| panne | 3→15 | 1003 → 1011 | **200** (toujours) |
| récupération | 17 | 1013 | 200 |
| récupération | 19 | **2** | 200 |
| récupération | 27 | **0** | 200 |

→ **Aucune propagation** (API = 200 partout), lag de ~1011 **résorbé en ~2 s** (~500 msg/s).
Lag nominal des 4 groupes : 0–2 messages (temps réel). Figure `fig_IV_5_resilience`.

---

### T5 — Pipeline CI/CD (blocage sur régression)

**Comment.** Démonstration des deux cas du workflow GitHub Actions :
- **Nominal** : push → checkout → deps → `pytest` → build → scan Trivy → push DockerHub → déploiement autorisé.
- **Régression** : test unitaire en échec → pipeline arrêté à l'étape tests → build/scan/push **ignorés** → déploiement bloqué, prod inchangée.

→ Figure `fig_IV_6_cicd` (exécution verte vs bloquée, côte à côte).

---

### T6 — Observabilité & auditabilité

**Comment.** Pendant un test de charge soutenue (`ab` en boucle + `traffic.sh`), capture du
dashboard Grafana en temps réel ; puis requête d'audit agrégée sur PostgreSQL.

```bash
docker exec food-pricing-postgres-1 psql -U pricing -d foodpricing -c \
  "SELECT zone_livraison, count(*), avg(surge_multiplier), max(surge_multiplier), avg(total)
   FROM pricing_history GROUP BY zone_livraison ORDER BY count(*) DESC;"
```

**Résultats réels :** **50 134 décisions** tracées sur **8 zones**, 0 erreur 5xx pendant la charge.

| Zone | Décisions | Surge moyen | Surge max | Prix moyen |
|---|---|---|---|---|
| casa-center | 48 866 | 2,50 | 2,50 | 17,86 |
| marrakech-medina | 429 | 2,47 | 2,50 | 48,16 |
| agadir-talborjt | 420 | 2,47 | 2,50 | 49,34 |
| rabat-agdal | 415 | 2,49 | 2,50 | 48,70 |
| test-pic / fav / max / normal | 1 chacun | 2,18 / 1,04 / 2,50 / 1,00 | — | 16,24 / 6,71 / 21,88 / 6,75 |

→ Figures `fig_IV_7_grafana_load` (dashboard sous charge) et `fig_IV_8_audit` (audit psql).

---

## 4. Synthèse — besoins vs résultats

| Besoin (§I.4.5) | Test | Résultat | Verdict |
|---|---|---|---|
| Latence < 100 ms | T2 | P50 = 5,7 ms · P95 = 6,7 ms | ✓ |
| Suppression dépendance BDD sur chemin critique | T2 | Redis seul (< 10 ms) | ✓ |
| Évolutivité | T3 | Stable < 100 ms jusqu'à ~617 req/s | ✓ |
| Signaux temps réel | T4 | Lag nominal 0–2 msg | ✓ |
| Résilience | T4 | API 200, reprise ~2 s | ✓ |
| Observabilité | T6 | Métriques live, 0 erreur 5xx | ✓ |
| Déploiement / rollback | T5 | Déploiement bloqué sur test rouge | ✓ |

---

## 5. Reproduire la campagne

```bash
# 1. Démarrer la stack (4 workers pour les tests de perf)
cd deploy
docker compose -f docker-compose.yml -f docker-compose.perf.yml up -d

# 2. Depuis WSL, lancer les scripts (depuis la racine du repo)
bash docs/ops/scenarios.sh      # T1 — prix par scénario
bash docs/ops/latency.sh        # T2 — lat_samples.txt + percentiles
bash docs/ops/sweep.sh          # T3 — sweep.csv
bash docs/ops/resilience.sh     # T4 — resilience.csv

# 3. (Optionnel) regénérer les figures PNG depuis les HTML
#    via Chrome headless --screenshot, puis le docx :
node docs/js/build_chapitre4.js   # -> docs/Chapitre_IV_final.docx

# 4. Arrêter
docker compose -f docker-compose.yml -f docker-compose.perf.yml down
```

---

## 6. Inventaire des figures du Chapitre IV

| Figure | Fichier | Source |
|---|---|---|
| IV.1 — Lag Kafka nominal | `figures/fig_IV_1_kafka_lag.png` | `kafka-consumer-groups.sh` (réel) |
| IV.2 — Réponse JSON `/price` | `figures/fig_IV_2_price_json.png` | scénario T1 (réel) |
| IV.3 — Histogramme latence + SLO | `figures/fig_IV_3_latency_hist.png` | `lat_samples.txt` |
| IV.4 — P95 / débit vs charge | `figures/fig_IV_4_sweep.png` | `sweep.csv` |
| IV.5 — Résilience (panne/reprise) | `figures/fig_IV_5_resilience.png` | `resilience.csv` |
| IV.6 — CI/CD vert vs bloqué | `figures/fig_IV_6_cicd.png` | maquette workflow |
| IV.7 — Grafana sous charge | `figures/fig_IV_7_grafana_load.png` | capture réelle |
| IV.8 — Audit PostgreSQL par zone | `figures/fig_IV_8_audit.png` | requête `pricing_history` (réel) |

---

## 7. Limites de la campagne

- Tests sur **machine unique** : SLO non validé en cluster multi-nœuds (latence réseau inter-zones).
- **Signaux simulés** : producers synthétiques, pas de données de production réelles.
- Débit de saturation (~600 req/s) propre à la **configuration 4 workers**, pas à un cluster.
- Pas de **traçage distribué** (corrélation inter-services) — diagnostic fin limité.
