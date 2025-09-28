from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Union

class RouteRequest(BaseModel):
    """Request model for the routing endpoint - specification format only"""
    tenant_id: str  # Required - multi-tenant identifier
    event_id: Optional[str] = None  # Optional - unique event identifier
    user_id: Optional[str] = None   # Optional - user identifier (used with ts if no event_id)
    payload_version: int = 1  # Required - payload version for compatibility
    type: Optional[str] = None  # Optional - event type (e.g., "breath_check_in")
    ts: Optional[str] = None  # Optional - timestamp, will use current time if not provided
    kind: Optional[str] = None  # Optional classification override
    
    # Everything else goes in the root (like biometrics, text, message, etc.)
    model_config = ConfigDict(
        extra="allow",  # Allow additional fields in root
        json_schema_extra={
            "example": {
                "tenant_id": "t1", 
                "event_id": "f0b8c5f2-8a0b-4b1d-9a9e-55b4f4c0b111",
                "user_id": "u1",
                "payload_version": 1,
                "type": "breath_check_in",
                "ts": "2025-09-20T10:20:30Z",
                "biometrics": {
                    "breath_rate_bpm": 22,
                    "hrv_ms": 48
                },
                "text": "Feeling tight in my chest"
            }
        }
    )

class RouteResponse(BaseModel):
    """Response model for the routing endpoint"""
    status: str
    routed_agents: List[str]
    trace_id: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "routed_agents": ["Axis"],
                "trace_id": "abcdef1234567890"
            }
        }
    )

class LogOut(BaseModel):
    """Log output model for the logs endpoint"""
    log_id: str
    timestamp: str
    sender_id: str
    kind: str
    routed_agents: List[str]
    response: Dict[str, Any]
    metadata: Dict[str, Any]

class HealthResponse(BaseModel):
    """Response model for the health endpoint"""
    status: str
    components: Dict[str, Dict[str, Any]]
    latency_ms: float

class HealthComponentStatus(BaseModel):
    """Component status model for the health endpoint"""
    status: str
    detail: Optional[str] = None

class DLQStatusResponse(BaseModel):
    """Response model for the DLQ status endpoint"""
    count: int
    oldest: Optional[str] = None
    max_attempts: Optional[int] = None
    unique_logs: Optional[int] = None
    reasons: Optional[List[Dict[str, Any]]] = None

class DLQItem(BaseModel):
    """Model for a DLQ item"""
    id: int
    log_id: str
    reason: str
    payload: Dict[str, Any]
    attempts: int
    ts: str
