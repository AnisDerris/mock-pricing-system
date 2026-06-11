#!/usr/bin/env bash
# Test de resilience : arret d'un consumer, accumulation du lag, redemarrage,
# resorption. L'API doit rester disponible (fallback Redis, pas de propagation).
set -u
KAFKA=food-pricing-kafka-1
GROUP=food-pricing-orders
OUT=/mnt/c/Users/ROG/Desktop/developpement/MockPricingSystem/docs/ops/resilience.csv
API="http://localhost:8000/price"
BODY='{"restaurant_id":"mcdo-casa-center","zone_livraison":"casa-center","adresse":"x","distance_km":3.5,"heure":12.5,"type_commande":"delivery"}'

lag() {
  docker exec "$KAFKA" /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --describe --group "$GROUP" 2>/dev/null | awk 'NR>1 && $6 ~ /^[0-9]+$/ {s+=$6} END{print s+0}'
}
api_code() { curl -s -o /dev/null -w "%{http_code}" -X POST "$API" -H "Content-Type: application/json" -d "$BODY"; }

echo "phase,t_s,lag,api_code" > "$OUT"
t=0
echo "[t=$t] baseline"
echo "nominal,$t,$(lag),$(api_code)" | tee -a "$OUT"

echo ">> arret de consumer-orders"
docker stop food-pricing-consumer-orders-1 >/dev/null

echo ">> injection d'un backlog (1000 messages orders-events)"
docker exec food-pricing-producer-1 python -c "
from kafka import KafkaProducer
import json
p=KafkaProducer(bootstrap_servers='kafka:9092', value_serializer=lambda v: json.dumps(v).encode())
for _ in range(1000):
    p.send('orders-events', {'event':'new_order','zone':'casa-center','restaurant_id':'mcdo-casa-center','delta':1,'ts':0})
p.flush()
print('1000 messages envoyes')
"

for k in 1 2 3 4 5; do
  t=$((t+3)); sleep 3
  echo "panne,$t,$(lag),$(api_code)" | tee -a "$OUT"
done

echo ">> redemarrage de consumer-orders"
docker start food-pricing-consumer-orders-1 >/dev/null
for k in $(seq 1 10); do
  t=$((t+2)); sleep 2
  L=$(lag); C=$(api_code)
  echo "recuperation,$t,$L,$C" | tee -a "$OUT"
  [ "$L" = "0" ] && { echo ">> lag resorbe"; break; }
done
echo "--- ecrit dans docs/ops/resilience.csv ---"
