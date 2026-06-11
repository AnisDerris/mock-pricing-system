#!/usr/bin/env bash
# Injecte des etats de marche deterministes dans Redis (zones de test isolees,
# non touchees par les producers) puis interroge /price SANS lat/lon
# (weather=1.0 immediat, pas d'appel externe) pour capturer le prix calcule.
set -u
API="http://localhost:8000"
R() { docker exec food-pricing-redis-1 redis-cli "$@" >/dev/null; }

price() {
  local rid="$1" zone="$2" km="$3" hr="$4"
  curl -s -X POST "$API/price" -H "Content-Type: application/json" \
    -d "{\"restaurant_id\":\"$rid\",\"zone_livraison\":\"$zone\",\"adresse\":\"test\",\"distance_km\":$km,\"heure\":$hr,\"type_commande\":\"delivery\"}"
}

set_scenario() {
  local zone="$1" rid="$2" orders="$3" drivers="$4" traffic="$5" load="$6" prep="$7"
  R SET "zone:${zone}:orders"  "$orders"  EX 600
  R SET "zone:${zone}:drivers" "$drivers" EX 600
  R SET "zone:${zone}:traffic" "$traffic" EX 600
  R SET "restaurant:${rid}:load" "$load" EX 600
  R SET "restaurant:${rid}:prep_time" "$prep" EX 600
  R SET "restaurant:${rid}:open" "1" EX 600
}

echo "=== T-normal (orders=5 drivers=8 traffic=1.0 load=0.0 heure=10) ==="
set_scenario test-normal rest-normal 5 8 1.0 0.0 15
price rest-normal test-normal 5 10 | jq -c .
echo

echo "=== T-pic-modere (orders=8 drivers=5 traffic=1.2 load=0.5 heure=13 dejeuner) ==="
set_scenario test-pic rest-pic 8 5 1.2 0.5 22
price rest-pic test-pic 5 13 | jq -c .
echo

echo "=== T-favorable (orders=2 drivers=12 traffic=1.0 load=0.1 heure=10) ==="
set_scenario test-fav rest-fav 2 12 1.0 0.1 12
price rest-fav test-fav 5 10 | jq -c .
echo

echo "=== T-pic-maximal (orders=40 drivers=1 traffic=2.0 load=1.0 heure=20 diner) ==="
set_scenario test-max rest-max 40 1 2.0 1.0 35
price rest-max test-max 5 20 | jq -c .
echo
