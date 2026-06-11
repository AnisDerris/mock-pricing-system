#!/usr/bin/env bash
# Montee en charge : debit et latence P95 a concurrence croissante.
set -u
API="http://localhost:8000/price"
BODY=/tmp/body.json
cat > "$BODY" <<'JSON'
{"restaurant_id":"mcdo-casa-center","zone_livraison":"casa-center","adresse":"x","distance_km":3.5,"heure":12.5,"type_commande":"delivery"}
JSON

OUT=/mnt/c/Users/ROG/Desktop/developpement/MockPricingSystem/docs/ops/sweep.csv
echo "concurrency,req_per_s,p50_ms,p95_ms,p99_ms,mean_ms" > "$OUT"

for c in 1 5 10 20 50 100 200; do
  res=$(ab -n 3000 -c "$c" -l -p "$BODY" -T application/json "$API" 2>/dev/null)
  [ -z "$res" ] && res=$(ab -n 3000 -c "$c" -p "$BODY" -T application/json "$API" 2>/dev/null)
  rps=$(echo "$res" | awk '/Requests per second/{print $4}')
  mean=$(echo "$res" | awk '/Time per request/{print $4; exit}')
  p50=$(echo "$res" | awk '/ 50%/{print $2}')
  p95=$(echo "$res" | awk '/ 95%/{print $2}')
  p99=$(echo "$res" | awk '/ 99%/{print $2}')
  echo "$c,$rps,$p50,$p95,$p99,$mean" | tee -a "$OUT"
done
echo "--- ecrit dans docs/ops/sweep.csv ---"
