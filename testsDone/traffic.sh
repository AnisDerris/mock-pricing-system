#!/usr/bin/env bash
# Génère du trafic continu vers l'API de pricing pour alimenter les dashboards.
set -u

ZONES=(casa-center rabat-agdal marrakech-medina agadir-talborjt)
RESTS=(mcdo-casa-center pizza-hut-agdal sushi-king-medina burger-house-casa le-petit-chef-agadir)
API="http://localhost:8000"

N="${1:-3000}"
for i in $(seq 1 "$N"); do
  z="${ZONES[$((RANDOM % ${#ZONES[@]}))]}"
  r="${RESTS[$((RANDOM % ${#RESTS[@]}))]}"
  km="$(( RANDOM % 40 + 1 )).$(( RANDOM % 9 ))"
  hr="$(( RANDOM % 24 )).$(( RANDOM % 9 ))"
  curl -s -o /dev/null -X POST "$API/price" -H "Content-Type: application/json" \
    -d "{\"restaurant_id\":\"$r\",\"zone_livraison\":\"$z\",\"adresse\":\"addr\",\"distance_km\":$km,\"heure\":$hr,\"type_commande\":\"delivery\",\"lat\":33.57,\"lon\":-7.59}"
  curl -s -o /dev/null "$API/zones/$z"
  curl -s -o /dev/null "$API/restaurants/$r"
  sleep 0.25
done
