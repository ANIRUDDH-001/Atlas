#!/usr/bin/env bash
# Atlas Smoke Test — run after `docker compose up`
# Verifies all endpoints return expected responses
# Exit code 0 = all tests passed, 1 = failure

set -euo pipefail

API="http://localhost:8000"
STORE="STORE_ST1008"
PASS=0
FAIL=0

green() { echo -e "\033[32m✓ $1\033[0m"; PASS=$((PASS+1)); }
red()   { echo -e "\033[31m✗ $1\033[0m"; FAIL=$((FAIL+1)); }

check() {
  local desc="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local expected_key="${4:-}"

  response=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null)
  status=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)

  if ! echo "$status" | grep -qE "^($expected_status)$"; then
    red "$desc — HTTP $status (expected $expected_status)"
    echo "    Body: ${body:0:200}"
    return
  fi

  if [ -n "$expected_key" ]; then
    if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$expected_key' in d" 2>/dev/null; then
      green "$desc"
    else
      red "$desc — response missing key '$expected_key'"
      echo "    Body: ${body:0:200}"
    fi
  else
    green "$desc"
  fi
}

echo "========================================="
echo "  Atlas Smoke Test"
echo "  API: $API"
echo "  Store: $STORE"
echo "========================================="
echo ""

# Wait for API to be ready
echo "Waiting for API..."
for i in $(seq 1 20); do
  if curl -sf "$API/health" > /dev/null 2>&1; then
    echo "API ready after ${i}s"
    break
  fi
  sleep 2
done

echo ""
echo "--- Core Endpoints ---"
check "GET /health"                         "$API/health"                      200 "status"
check "GET /stores/{id}/metrics"            "$API/stores/$STORE/metrics"       200 "unique_visitors"
check "GET /stores/{id}/funnel"             "$API/stores/$STORE/funnel"        200 "funnel"
check "GET /stores/{id}/anomalies"          "$API/stores/$STORE/anomalies"     200 "anomalies"
check "GET /stores/{id}/heatmap"            "$API/stores/$STORE/heatmap"       200

echo ""
echo "--- Ingestion ---"
SAMPLE_EVENT='{
  "events": [{
    "event_id": "'$(python3 -c "import uuid; print(uuid.uuid4())")'",
    "store_id": "'$STORE'",
    "camera_id": "CAM_ENTRY_01",
    "visitor_id": "VIS_SMOKE",
    "event_type": "ENTRY",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "zone_id": null,
    "confidence": 0.92,
    "metadata": {
      "queue_depth": null,
      "session_seq": 1
    }
  }]
}'

ingest_resp=$(curl -s -X POST "$API/events/ingest" \
  -H "Content-Type: application/json" \
  -d "$SAMPLE_EVENT")
accepted=$(echo "$ingest_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accepted',0))" 2>/dev/null)

if [ "$accepted" -ge "1" ] 2>/dev/null; then
  green "POST /events/ingest — accepted=$accepted"
else
  red "POST /events/ingest — accepted=$accepted, response: ${ingest_resp:0:200}"
fi

# Idempotency check
ingest_resp2=$(curl -s -X POST "$API/events/ingest" \
  -H "Content-Type: application/json" \
  -d "$SAMPLE_EVENT")
accepted2=$(echo "$ingest_resp2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accepted',0))" 2>/dev/null)

if [ "$accepted2" -eq "0" ] 2>/dev/null; then
  green "POST /events/ingest idempotency — duplicate rejected (accepted=0)"
else
  red "POST /events/ingest idempotency — duplicate was accepted (accepted=$accepted2)"
fi

echo ""
echo "--- Metrics Quality ---"
metrics=$(curl -s "$API/stores/$STORE/metrics")

# unique_visitors must be a non-negative integer
uv=$(echo "$metrics" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unique_visitors','MISSING'))" 2>/dev/null)
if echo "$uv" | grep -qE '^[0-9]+$'; then
  green "unique_visitors is integer: $uv"
else
  red "unique_visitors is not an integer: $uv"
fi

# data_confidence must be present
dc=$(echo "$metrics" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data_confidence','MISSING'))" 2>/dev/null)
if [ "$dc" = "HIGH" ] || [ "$dc" = "LOW" ]; then
  green "data_confidence present: $dc"
else
  red "data_confidence missing or invalid: $dc"
fi

# current_queue_depth must be a non-negative integer
qd=$(echo "$metrics" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('current_queue_depth','MISSING'))" 2>/dev/null)
if echo "$qd" | grep -qE '^[0-9]+$'; then
  green "current_queue_depth is integer: $qd"
else
  red "current_queue_depth is not an integer: $qd"
fi

echo ""
echo "--- Error Handling ---"
check "GET unknown store — should not 500"  "$API/stores/STORE_UNKNOWN/metrics"  200
check "GET malformed store id"              "$API/stores/../../etc/metrics"           "400|404|422"

echo ""
echo "========================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================="

if [ "$FAIL" -gt "0" ]; then
  exit 1
fi
exit 0
