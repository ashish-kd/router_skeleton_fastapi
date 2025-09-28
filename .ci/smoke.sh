#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Router Service Smoke Test"

# Start services
docker compose up -d --build
echo "⏳ Waiting for services to be ready..."
sleep 15

# Health check
echo "🔍 Checking health endpoint..."
curl -fsS http://localhost:8000/health >/dev/null
echo "✅ Health check passed"

# Test main routing functionality
echo "🔍 Testing main routing..."
curl -fsS -X POST http://localhost:8000/route \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key' \
  -d '{
    "tenant_id": "smoke-test",
    "event_id": "smoke-event-123", 
    "user_id": "smoke-user",
    "payload_version": 1,
    "type": "assist",
    "text": "Smoke test - help needed urgently"
  }' | grep -E "(success|routed_to_dlq)" >/dev/null
echo "✅ Routing test passed"

# Test duplicate detection (idempotency)
echo "🔍 Testing duplicate detection..."
RESPONSE=$(curl -fsS -X POST http://localhost:8000/route \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-key' \
  -d '{
    "tenant_id": "smoke-test",
    "event_id": "smoke-event-123", 
    "user_id": "smoke-user", 
    "payload_version": 1,
    "type": "assist",
    "text": "Smoke test - help needed urgently"
  }')

if echo "$RESPONSE" | grep -q "already_processed"; then
  echo "✅ Duplicate detection test passed"
else
  echo "❌ Duplicate detection test failed"
  echo "Response: $RESPONSE"
  exit 1
fi

# Test metrics endpoint
echo "🔍 Testing metrics..."
curl -fsS http://localhost:8000/metrics | grep -E "router_ingress_total|router_rejected_total" >/dev/null
echo "✅ Metrics test passed"

# Test DLQ replay
echo "🔍 Testing DLQ replay..."
curl -fsS -X POST "http://localhost:8000/dlq/replay?limit=1" -H "X-API-Key: dev-key" >/dev/null
echo "✅ DLQ replay test passed"

echo "🎉 All smoke tests passed!"
echo "SMOKE OK - Router service is healthy!"