from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_client import Counter, Histogram, Gauge

# Main instrumentator
instrumentator = Instrumentator()

# Custom metrics as required
signals_received_total = Counter(
    "signals_received_total",
    "Total number of signals received by router",
    ["kind"]
)

router_latency_seconds = Histogram(
    "router_latency_seconds",
    "Router processing latency in seconds",
    ["kind"],
    buckets=[0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

routing_errors_total = Counter(
    "routing_errors_total",
    "Total number of routing errors",
    ["kind", "agent"]
)

dlq_total = Counter(
    "dlq_total",
    "Total number of messages sent to DLQ",
    ["reason"]
)

retry_attempts_total = Counter(
    "retry_attempts_total",
    "Total number of retry attempts",
    ["kind", "agent"]
)

dlq_backlog = Gauge(
    "dlq_backlog",
    "Current number of messages in DLQ"
)

# Add custom metrics to the instrumentator
def setup_metrics():
    # Add default metrics with enhanced granularity
    instrumentator.add(
        metrics.request_size(should_include_handler=True, should_include_method=True)
    )
    instrumentator.add(
        metrics.response_size(should_include_handler=True, should_include_method=True)
    )
    instrumentator.add(
        metrics.latency(should_include_handler=True, should_include_method=True)
    )
    instrumentator.add(
        metrics.requests(should_include_handler=True, should_include_method=True)
    )
