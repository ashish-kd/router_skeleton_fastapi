# Production-Ready Router Service

A high-performance router service that classifies incoming signals and routes them to the appropriate downstream agents with stable ≤5ms p50 latency, full observability, and durable logging.

## Quick Start (Local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb
export API_KEY=dev-key
alembic upgrade head
make dev
```

- Health: `GET /health`
- Route: `POST /route` (requires `X-API-Key: dev-key`)
- Metrics: `/metrics` (Prometheus)
- Logs: `GET /logs?sender_id=...`

### Sample request
```bash
curl -X POST http://localhost:8000/route \  -H "Content-Type: application/json" -H "X-API-Key: dev-key" \  -d '{
    "sender_id":"user_123",
    "payload":{"message":"help me understand policy"}
  }'
```

## Docker Compose (DB + Prometheus + Grafana + App)

```bash
docker compose up --build
# In another terminal run migrations
docker compose exec router alembic upgrade head
```

- Postgres: `localhost:5432`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin default)
- Router: `http://localhost:8000`

## Make targets
- `make dev` – hot reload server
- `make migrate` – run alembic migrations
- `make load` – basic load generator (`N=1000`)
- `make replay-dlq` – replay oldest DLQ items

## Features

### Signal Classification & Routing
- Heuristic rule-based classifier to determine signal kind based on payload content
- Deterministic routing table that maps signal kinds to agent endpoints
- Fan-out with bounded parallelism (configurable concurrency limit)
- Support for both first-success and aggregated multi-agent responses
- Idempotency through deterministic log_id generation

### Durability & Resilience
- Exponential backoff retries (configurable max attempts)
- Dead letter queue (DLQ) for failed requests
- DLQ replay functionality with retry management
- Strong idempotency guarantees through log_id deduplication

### Observability
- Comprehensive Prometheus metrics:
  - `signals_received_total` - Count of incoming signals by kind
  - `router_latency_seconds` - Processing time histograms by kind
  - `routing_errors_total` - Count of routing errors by agent
  - `dlq_total` - Count of messages sent to DLQ
  - `retry_attempts_total` - Count of retry attempts
  - `dlq_backlog` - Current count of messages in DLQ
- Grafana dashboard with SLO tracking for p50/p95 latency
- Structured JSON logging with trace_id for request tracking
- Health checks for service and database

### Performance
- Optimized for <5ms p50 latency
- Asynchronous agent calls for maximum throughput
- Connection pooling for database operations
- Low memory footprint

## Architecture
- FastAPI web server for high-performance async request handling
- Postgres for durable logs and DLQ storage
- Prometheus for metrics collection
- Grafana for visualization
- Structured logging with trace IDs

## Notes
- Deterministic `log_id` generated from `{sender_id, timestamp, payload_hash}` when missing
- JSONB columns for `routed_agents`, `response`, and `metadata` allow future expansion
- Trace IDs propagated to downstream agents for distributed tracing
- Metrics exposed via Prometheus endpoint for centralized monitoring
