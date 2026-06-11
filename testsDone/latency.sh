#!/usr/bin/env bash
# Latence reelle du chemin de calcul (/price sans lat/lon -> weather=1.0 immediat).
set -u
API="http://localhost:8000/price"
BODY=/tmp/body.json
cat > "$BODY" <<'JSON'
{"restaurant_id":"mcdo-casa-center","zone_livraison":"casa-center","adresse":"x","distance_km":3.5,"heure":12.5,"type_commande":"delivery"}
JSON

echo "### 1) Verification codes HTTP (500 requetes) ###"
for i in $(seq 1 500); do curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API" -H "Content-Type: application/json" -d @"$BODY"; done | sort | uniq -c

echo
echo "### 2) Warmup ###"
ab -n 300 -c 5 -p "$BODY" -T application/json "$API" >/dev/null 2>&1

echo "### 3) Latence chemin (concurrence 1, 1500 requetes, echantillons bruts ms) ###"
: > /tmp/lat.txt
for i in $(seq 1 1500); do
  t=$(curl -s -o /dev/null -w "%{time_total}" -X POST "$API" -H "Content-Type: application/json" -d @"$BODY")
  awk -v t="$t" 'BEGIN{printf "%.3f\n", t*1000}' >> /tmp/lat.txt
done
echo "samples=$(wc -l < /tmp/lat.txt)"
sort -n /tmp/lat.txt > /tmp/lat_sorted.txt
awk '{a[NR]=$1} END{
  n=NR;
  i50=int(0.50*n); i90=int(0.90*n); i95=int(0.95*n); i99=int(0.99*n);
  s=0; for(k=1;k<=n;k++) s+=a[k];
  printf "n=%d  mean=%.2f  min=%.2f  P50=%.2f  P90=%.2f  P95=%.2f  P99=%.2f  max=%.2f\n", n, s/n, a[1], a[i50], a[i90], a[i95], a[i99], a[n];
}' /tmp/lat_sorted.txt
cp /tmp/lat.txt /mnt/c/Users/ROG/Desktop/developpement/MockPricingSystem/docs/ops/lat_samples.txt
echo "samples copies -> docs/ops/lat_samples.txt"
