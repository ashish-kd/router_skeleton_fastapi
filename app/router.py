import hashlib
import json
import time
import uuid
import asyncio
import httpx
from typing import List, Tuple, Dict, Any, Optional, Union
from aiocache import cached
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.metrics import (
    SIGNALS_RECEIVED, ROUTER_LATENCY, ROUTING_ERRORS,
    DLQ_TOTAL, AGENT_HEALTH, timer
)
from app.utils import (
    with_retry, execute_parallel, circuit_breaker, 
    rate_limiter, logger, cache
)

# Agent configuration - would normally be in database or config
KIND_MAP = {
    "assist": ["Axis"],
    "policy": ["M"],
    "emergency": ["M", "Axis"],
    "unknown": ["DLQ"]
}

# Agent endpoints - pointing to mock agents service in Docker network
AGENT_ENDPOINTS = {
    "Axis": "http://mock-agents:8001/route",   # Docker service - fast response
    "M": "http://mock-agents:8001/process",    # Docker service - fast response  
    "DLQ": None  # Special case, handled internally
}

# Keywords for classification
KEYWORDS = {
    "emergency": ["urgent", "911", "crisis", "panic", "immediately"],
    "policy": ["policy", "compliance", "consent", "hipaa", "gdpr"],
    "assist": ["help", "assist", "question", "explain", "clarify"]
}

# Enhanced classifier with confidence scoring
@cached(ttl=300, namespace="classifier")
async def classify(payload: dict) -> Tuple[str, float]:
    """
    Classify the payload based on keywords with confidence scoring
    Returns (kind, confidence)
    """
    text = json.dumps(payload).lower()
    
    # Score each kind based on keyword matches
    scores = {}
    for kind, kws in KEYWORDS.items():
        score = sum(3 if k in text else 0 for k in kws) / (len(kws) * 3)
        if score > 0:
            scores[kind] = min(score + 0.5, 0.99)  # Base confidence + match score
    
    # Return highest score or unknown
    if scores:
        best_kind = max(scores.items(), key=lambda x: x[1])
        return best_kind[0], best_kind[1]
        
    return "unknown", 0.5

# Cache agent map for 5 minutes
@cached(ttl=300, namespace="agents")
async def agents_for(kind: str) -> List[str]:
    """Get list of agents for a given kind"""
    return KIND_MAP.get(kind, ["DLQ"])

def deterministic_log_id(sender_id: str, ts_iso: str, payload: dict) -> str:
    """Generate a deterministic log_id from inputs"""
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"{sender_id}:{ts_iso}:{h}"

def now_iso() -> str:
    """Get current UTC time in ISO format"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def new_trace_id() -> str:
    """Generate a new trace ID"""
    return uuid.uuid4().hex

# Agent communication with retry and circuit breaking
@with_retry(max_attempts=3)  # Max 3 tries as per specification
async def call_agent(
    agent: str, 
    payload: Dict[str, Any],
    trace_id: str,
    timeout: float = 2.0  # 2 second timeout for reliable connections
) -> Dict[str, Any]:
    """Call an agent with the payload, with retry and circuit breaking"""
    # Check circuit breaker
    if circuit_breaker.is_circuit_open(agent):
        logger.warning("Circuit open, skipping agent", 
                     agent=agent, trace_id=trace_id)
        raise Exception(f"Circuit open for agent {agent}")
    
    # Special case for DLQ
    if agent == "DLQ":
        return {"status": "queued_for_dlq"}
    
    endpoint = AGENT_ENDPOINTS.get(agent)
    if not endpoint:
        ROUTING_ERRORS.labels(error_type="missing_endpoint", agent=agent).inc()
        raise Exception(f"No endpoint configured for agent {agent}")
    
    try:
        # Use httpx for async HTTP requests
        async with httpx.AsyncClient() as client:
            with timer(operation="agent_call", kind=agent):
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"X-Trace-ID": trace_id},
                    timeout=timeout
                )
        
        if response.status_code >= 200 and response.status_code < 300:
            # Record success for circuit breaker
            circuit_breaker.record_success(agent)
            AGENT_HEALTH.labels(agent=agent).set(1)
            return response.json()
        else:
            # Record failure for circuit breaker
            circuit_breaker.record_failure(agent)
            AGENT_HEALTH.labels(agent=agent).set(0)
            ROUTING_ERRORS.labels(error_type="status_error", agent=agent).inc()
            raise Exception(f"Agent {agent} returned status {response.status_code}")
    except Exception as e:
        # Record failure for circuit breaker
        circuit_breaker.record_failure(agent)
        AGENT_HEALTH.labels(agent=agent).set(0)
        ROUTING_ERRORS.labels(error_type="call_error", agent=agent).inc()
        logger.error("Agent call failed", 
                   agent=agent, 
                   error=str(e),
                   trace_id=trace_id)
        raise

async def add_to_dlq(
    db: AsyncSession, 
    log_id: str, 
    reason: str, 
    payload: Dict[str, Any],
    max_retries: int = 3
) -> bool:
    """
    Add an item to the dead letter queue with retries and fallback logging
    Returns True if successful, False otherwise
    """
    for attempt in range(max_retries):
        try:
            DLQ_TOTAL.labels(reason=reason).inc()
            
            # Raw SQL insert to avoid issues with parameter binding
            payload_json = json.dumps(payload).replace("'", "''")
            sql = f"""
            INSERT INTO dlq (log_id, reason, payload, attempts)
            VALUES ('{log_id}', '{reason}', '{payload_json}'::jsonb, 0)
            """
            await db.execute(text(sql))
            await db.commit()
            
            logger.info("Added to DLQ", log_id=log_id, reason=reason)
            return True
            
        except Exception as e:
            logger.error(
                "DLQ operation failed", 
                log_id=log_id, 
                reason=reason,
                attempt=attempt + 1,
                error=str(e)
            )
            
            if attempt < max_retries - 1:
                # Wait before retry with exponential backoff
                await asyncio.sleep(0.1 * (2 ** attempt))
                
                # Try to rollback the transaction
                try:
                    await db.rollback()
                except:
                    pass
            else:
                # Final attempt failed - log to structured logs as fallback
                logger.critical(
                    "DLQ operation permanently failed - using fallback logging", 
                    log_id=log_id,
                    reason=reason,
                    payload=payload,
                    event="dlq_fallback"
                )
                return False
    
    return False

async def route_to_agents(
    db: AsyncSession,
    log_id: str,
    kind: str,
    payload: Dict[str, Any],
    trace_id: str
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Route payload to appropriate agents with parallel execution
    Returns (routed_agents, response)
    """
    # Record metric
    SIGNALS_RECEIVED.labels(kind=kind, sender_id=payload.get("sender_id", "unknown")).inc()
    
    with timer(operation="route_to_agents", kind=kind):
        # Determine agents to route to
        agents = await agents_for(kind)
        
        if not agents:
            dlq_success = await add_to_dlq(db, log_id, "no_agents_for_kind", payload)
            return ["DLQ"], {
                "status": "no_agents_available",
                "dlq_logged": dlq_success
            }
        
        # If DLQ is the only agent, just return
        if agents == ["DLQ"]:
            dlq_success = await add_to_dlq(db, log_id, "routed_to_dlq", payload)
            return agents, {
                "status": "routed_to_dlq",
                "dlq_logged": dlq_success
            }
        
        # Add trace_id to payload for downstream tracing
        enriched_payload = {**payload, "trace_id": trace_id}
        
        # Execute agent calls in parallel with bounded concurrency
        results = await execute_parallel(
            lambda agent: call_agent(agent, enriched_payload, trace_id),
            agents,
            max_concurrency=5,
            timeout=3.0  # 3 second total timeout for reliable connections
        )
        
        # Process results
        successful_agents = []
        failed_agents = []
        responses = {}
        
        for agent, result in zip(agents, results):
            if result is not None:
                successful_agents.append(agent)
                responses[agent] = result
            else:
                failed_agents.append(agent)
        
        # If all failed, add to DLQ
        if not successful_agents and failed_agents:
            dlq_success = await add_to_dlq(db, log_id, "all_agents_failed", payload)
            return ["DLQ"], {
                "status": "all_agents_failed", 
                "failed": failed_agents,
                "dlq_logged": dlq_success
            }
        
        # Return aggregated response
        return successful_agents, {
            "status": "success", 
            "successful": successful_agents,
            "failed": failed_agents,
            "responses": responses
        }
