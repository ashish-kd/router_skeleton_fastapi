from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Union

class RouteRequest(BaseModel):
    """Request model for the routing endpoint"""
    log_id: Optional[str] = None
    timestamp: Optional[str] = None
    sender_id: str
    payload: Dict[str, Any]
    kind: Optional[str] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sender_id": "user_123",
                "payload": {"message": "Help me understand policy"},
                "kind": None,  # Optional, will be auto-detected if not provided
                "log_id": None,  # Optional, will be auto-generated if not provided
                "timestamp": None  # Optional, will use current time if not provided
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
