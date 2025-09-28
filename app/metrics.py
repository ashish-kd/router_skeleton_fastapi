import time
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# Router metrics per specification - ONLY these are needed
ROUTER_INGRESS_TOTAL = Counter(
    "router_ingress_total", 
    "Total number of requests received by router",
    ["type"]
)

ROUTER_LATENCY_SECONDS = Histogram(
    "router_latency_seconds",
    "Time taken for routing operations",
    ["operation", "kind"],
    buckets=[0.001, 0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
)

ROUTER_DOWNSTREAM_SUCCESS_TOTAL = Counter(
    "router_downstream_success_total",
    "Total number of successful downstream calls",
    ["service"]
)

ROUTER_DOWNSTREAM_FAIL_TOTAL = Counter(
    "router_downstream_fail_total",
    "Total number of failed downstream calls",
    ["service", "reason"]
)

ROUTER_DLQ_TOTAL = Counter(
    "router_dlq_total",
    "Total number of items sent to DLQ",
    ["reason"]
)

ROUTER_REPLAY_RUNS_TOTAL = Counter(
    "router_replay_runs_total",
    "Total number of DLQ replay runs",
    ["mode"]
)

ROUTER_REPLAY_ITEMS_TOTAL = Counter(
    "router_replay_items_total",
    "Total number of DLQ replay items processed",
    ["mode", "outcome"]
)

ROUTER_REPLAY_RATE_LIMITED_TOTAL = Counter(
    "router_replay_rate_limited_total",
    "Total number of rate limited replay operations"
)

ROUTER_REJECTED_TOTAL = Counter(
    "router_rejected_total",
    "Total number of rejected requests", 
    ["reason"]
)

# Additional operational metrics (not in specification but needed for operations)
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

def timer(operation, kind="unknown"):
    """Timer context manager for measuring operation duration"""
    return TimerContextManager(ROUTER_LATENCY_SECONDS, {"operation": operation, "kind": kind})
