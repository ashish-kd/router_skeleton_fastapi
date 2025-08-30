import hashlib, json, time, uuid
from typing import List, Tuple

KIND_MAP = {
    "assist": ["Axis"],
    "policy": ["M"],
    "emergency": ["M", "Axis"],
    "unknown": ["DLQ"]
}

KEYWORDS = {
    "emergency": ["urgent", "911", "crisis", "panic", "immediately"],
    "policy": ["policy", "compliance", "consent", "hipaa", "gdpr"],
    "assist": ["help", "assist", "question", "explain", "clarify"]
}

def classify(payload: dict) -> Tuple[str, float]:
    text = json.dumps(payload).lower()
    for kind, kws in KEYWORDS.items():
        if any(k in text for k in kws):
            return kind, 0.9
    return "unknown", 0.5

def agents_for(kind: str) -> List[str]:
    return KIND_MAP.get(kind, ["DLQ"])

def deterministic_log_id(sender_id: str, ts_iso: str, payload: dict) -> str:
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"{sender_id}:{ts_iso}:{h}"

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def new_trace_id() -> str:
    return uuid.uuid4().hex