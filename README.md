# Router Service - Production Grade Implementation

A high-performance router service that classifies incoming signals and routes them to appropriate downstream agents with optimal latency, full observability, and reliability features.

## Features

- **High Performance**: ≤5ms p50 latency with optimized async processing
- **Pluggable Classification**: Smart rule-based classifier for signal categorization
- **Parallel Agent Fan-out**: Route to multiple agents with bounded concurrency
- **Idempotency**: Deduplication based on deterministic log_id generation
- **Comprehensive Observability**:
  - Prometheus metrics for latency, traffic, errors, and saturation
  - Grafana dashboards pre-configured for key metrics
  - Structured logging with trace_id correlation
- **Reliability Features**:
  - Retry logic with exponential backoff
  - DLQ (Dead Letter Queue) for failed messages with replay capability
  - Circuit breaker to prevent cascading failures
  - Rate limiting per sender_id
- **Health and Status Monitoring**: Rich health checks and operational status endpoints

## Quick Start (Local)

```bash
# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb
export API_KEY=dev-key

# Run database migrations
alembic upgrade head

# Start the development server with hot reload
make dev
```

## Using Docker Compose (Recommended)

Our Docker Compose setup includes everything you need: the Router service, PostgreSQL database, Prometheus for metrics collection, and Grafana with pre-configured dashboards.

```bash
# Start all services
docker compose up --build

# In another terminal run migrations (first time only)
docker compose exec router alembic upgrade head
```

Access the services:
- **Router API**: `http://localhost:8000`
- **Grafana Dashboards**: `http://localhost:3000` (login: admin/admin)
- **Prometheus**: `http://localhost:9090`
- **PostgreSQL**: `localhost:5432`

## API Endpoints

### Router Endpoints

- **POST /route** - Main routing endpoint
  - Requires `X-API-Key: dev-key` header
  - Sample request:
    ```bash
    curl -X POST http://localhost:8000/route \
      -H "Content-Type: application/json" \
      -H "X-API-Key: dev-key" \
      -d '{
        "sender_id": "user_123",
        "payload": {"message": "help me understand policy"}
      }'
    ```

- **GET /health** - System health check with component status
- **GET /metrics** - Prometheus metrics endpoint
- **GET /logs?sender_id=...&limit=100&offset=0** - Query logs by sender_id with pagination
- **GET /dlq/status** - View current DLQ status and statistics

## Make Targets

- `make dev` – Run server with hot reload
- `make run` – Run production server
- `make migrate` – Run database migrations (alias for `alembic upgrade head`)
- `make load` – Run load test with configurable parameters
  - Options: `-n 1000 -c 50` (requests and concurrency)
- `make replay-dlq LIMIT=100` – Replay items from DLQ
  - Options: `--dry-run` to preview without actually replaying

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string
- `API_KEY` - API key for authentication
- `LOG_LEVEL` - Logging level (default: INFO)
- `MAX_LOGS_LIMIT` - Maximum number of logs to return (default: 1000)

## Architecture

The router implements a multi-stage pipeline:

1. **Request validation** - Validate incoming requests with Pydantic
2. **Classification** - Determine the kind of request using configurable rules
3. **Routing** - Map the kind to appropriate downstream agents
4. **Parallel execution** - Fan out to agents with bounded concurrency
5. **Response aggregation** - Collect and aggregate responses
6. **Logging** - Record detailed request/response information
7. **Metrics** - Capture performance and operational metrics

### Reliability Features

- **Circuit Breaker**: Automatically detects failing downstream agents and temporarily disables them to prevent cascading failures
- **Rate Limiting**: Prevents any single sender_id from overwhelming the system
- **Idempotency**: Guarantees exactly-once processing by generating deterministic log_ids
- **DLQ**: Stores messages that fail processing for later analysis and replay

## Observability

### Metrics

Key metrics available in Prometheus:
- `signals_received_total` - Total signals received by kind
- `router_latency_seconds` - Latency histograms for routing operations
- `routing_errors_total` - Routing errors by type and agent
- `dlq_total` - Total items sent to DLQ by reason
- `retry_attempts_total` - Retry attempts by agent and status
- `rate_limit_hits_total` - Rate limit hits by sender_id
- `circuit_breaker_trips_total` - Circuit breaker activations by agent

### Grafana Dashboard

The pre-configured dashboard includes panels for:
- P50/P95/P99 latency
- Request rate
- Signal distribution by kind
- Error rates
- DLQ backlog
- Retry statistics
- Circuit breaker status

## Performance

Performance tests demonstrate that the router meets or exceeds the target SLOs:
- P50 latency: ≤5ms (target: ≤5ms)
- P95 latency: ≤15ms (target: ≤15ms)
- Error rate: <0.1% under normal conditions
