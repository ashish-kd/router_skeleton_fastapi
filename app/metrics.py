import time
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# Create custom metrics
SIGNALS_RECEIVED = Counter(
    "signals_received_total", 
    "Total number of signals received",
    ["kind", "sender_id"]
)

ROUTER_LATENCY = Histogram(
    "router_latency_seconds",
    "Time taken for routing operations",
    ["operation", "kind"],
    buckets=[0.001, 0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
)

ROUTING_ERRORS = Counter(
    "routing_errors_total",
    "Total number of routing errors",
    ["error_type", "agent"]
)

DLQ_TOTAL = Counter(
    "dlq_total",
    "Total number of items in DLQ",
    ["reason"]
)

RETRY_ATTEMPTS = Counter(
    "retry_attempts_total",
    "Total number of retry attempts",
    ["agent", "status"]
)

AGENT_HEALTH = Gauge(
    "agent_health",
    "Health status of downstream agents",
    ["agent"]
)

RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Total number of rate limit hits",
    ["sender_id"]
)

CIRCUIT_BREAKER_TRIPS = Counter(
    "circuit_breaker_trips_total",
    "Total number of circuit breaker trips",
    ["agent"]
)

DLQ_BACKLOG = Gauge(
    "dlq_backlog",
    "Current number of items in DLQ"
)

# Performance timer context manager
class TimerContextManager:
    def __init__(self, metric, labels=None):
        self.metric = metric
        self.labels = labels or {}
        self.start = None
        
    def __enter__(self):
        self.start = time.perf_counter()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start:
            duration = time.perf_counter() - self.start
            self.metric.labels(**self.labels).observe(duration)

# Set up instrumentator with custom metrics
instrumentator = Instrumentator()
instrumentator.add(metrics.default())
instrumentator.add(metrics.requests())

def custom_metrics():
    return instrumentator

def timer(operation, kind="unknown"):
    """Timer context manager for measuring operation duration"""
    return TimerContextManager(ROUTER_LATENCY, {"operation": operation, "kind": kind})
