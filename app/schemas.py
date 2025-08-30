from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class RouteRequest(BaseModel):
    log_id: Optional[str] = None
    timestamp: Optional[str] = None
    sender_id: str
    payload: Dict[str, Any]
    kind: Optional[str] = None

class RouteResponse(BaseModel):
    status: str
    routed_agents: List[str]
    trace_id: str

class LogOut(BaseModel):
    log_id: str
    timestamp: str
    sender_id: str
    kind: str
    routed_agents: List[str]
    response: Dict[str, Any]
    metadata: Dict[str, Any]
