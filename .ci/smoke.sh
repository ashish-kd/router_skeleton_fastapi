#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Router Service Smoke Test"

# Start services with fresh database
docker compose down -v 2>/dev/null || true
docker compose up -d --build
echo "⏳ Waiting for services to be ready..."
sleep 15

# Run database migrations
echo "🔧 Running database migrations..."
docker compose exec -T router alembic upgrade head

# Health check
echo "🔍 Checking health endpoint..."
curl -fsS http://localhost:8000/health >/dev/null
echo "✅ Health check passed"

# Generate JWT tokens for testing
echo "🔑 Generating JWT tokens for testing..."
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: smoke-test' \
  -d '{"tenant": "smoke-test", "roles": ["admin"], "sub": "smoke-admin"}' | \
  jq -r '.token')

SERVICE_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: smoke-test' \
  -d '{"tenant": "smoke-test", "roles": ["service"], "sub": "smoke-service"}' | \
  jq -r '.token')

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "null" ]; then
  echo "❌ Failed to generate admin token"
  exit 1
fi

if [ -z "$SERVICE_TOKEN" ] || [ "$SERVICE_TOKEN" = "null" ]; then
  echo "❌ Failed to generate service token"
  exit 1
fi

echo "✅ JWT tokens generated successfully"

# Test main routing functionality
echo "🔍 Testing main routing..."
curl -fsS -X POST http://localhost:8000/route \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H 'X-Tenant-Id: smoke-test' \
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
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H 'X-Tenant-Id: smoke-test' \
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
curl -fsS -X POST "http://localhost:8000/dlq/replay?limit=1" \
  -H "Authorization: Bearer $ADMIN_TOKEN" >/dev/null
echo "✅ DLQ replay test passed"

echo "🎉 All smoke tests passed!"
echo "SMOKE OK - Router service is healthy!"