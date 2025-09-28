import os
import json
import time
import asyncio
import httpx
from typing import List, Optional, Dict, Any, Union
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, execute_query, AsyncSessionLocal
from app.metrics import instrumentator, timer, ROUTER_LATENCY_SECONDS, DLQ_BACKLOG, ROUTER_REJECTED_TOTAL
from app.schemas import RouteRequest, RouteResponse, LogOut, HealthResponse
from app.utils import rate_limiter, logger
from app.logging import TraceMiddleware, init_logging
from app.router import (
    classify, agents_for, now_iso, 
    new_trace_id, route_to_agents, generate_canonical_message_id, check_message_duplicate
)

# Configuration
API_KEY = os.getenv("API_KEY", "dev-key")
MAX_LOGS_LIMIT = int(os.getenv("MAX_LOGS_LIMIT", "1000"))

# Auto-replay configuration
ENABLE_AUTO_REPLAY = os.getenv("ENABLE_AUTO_REPLAY", "true").lower() == "true"
AUTO_REPLAY_INTERVAL = int(os.getenv("AUTO_REPLAY_INTERVAL", "600"))  # 10 minutes default
AUTO_REPLAY_BATCH_SIZE = int(os.getenv("AUTO_REPLAY_BATCH_SIZE", "50"))  # 50 messages per batch
MOCK_AGENTS_URL = os.getenv("MOCK_AGENTS_URL", "http://mock-agents:8001")

# Initialize structured logging
init_logging()

# Initialize FastAPI app
app = FastAPI(title="Router Service", version="1.0.0")

# Set up Prometheus metrics
instrumentator.instrument(app).expose(app, include_in_schema=True, should_gzip=True)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trace middleware for request tracing
app.add_middleware(TraceMiddleware)

@app.on_event("startup")
async def startup_event():
    # Update DLQ count periodically in background
    asyncio.create_task(update_dlq_metrics())
    
    # Start automated DLQ replay if enabled
    if ENABLE_AUTO_REPLAY:
        logger.info(f"Starting automated DLQ replay (interval: {AUTO_REPLAY_INTERVAL}s, batch size: {AUTO_REPLAY_BATCH_SIZE})")
        asyncio.create_task(auto_replay_dlq())

@app.on_event("shutdown")
async def shutdown_event():
    # Clean up resources
    pass

# Background task to periodically update DLQ count
async def update_dlq_metrics():
    while True:
        try:
            # Use a new session for each check
            async with AsyncSessionLocal() as session:
                # Using raw SQL without parameters
                result = await session.execute(text("SELECT COUNT(*) FROM dlq"))
                count = result.scalar_one() or 0
                DLQ_BACKLOG.set(count)
        except Exception as e:
            logger.error("Failed to update DLQ metrics", error=str(e))
        
        # Update every minute
        await asyncio.sleep(60)

async def check_agents_health() -> bool:
    """Check if downstream agents are responding"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{MOCK_AGENTS_URL}/health")
            if response.status_code == 200:
                health_data = response.json()
                return health_data.get("status") == "ok"
            return False
    except Exception as e:
        logger.warning(f"Agent health check failed: {e}")
        return False

async def auto_replay_dlq():
    """Automatically replay DLQ messages when agents are healthy"""
    logger.info("Automated DLQ replay task started")
    
    while True:
        try:
            # Check if agents are healthy before attempting replay
            if await check_agents_health():
                # Check current DLQ count
                async with AsyncSessionLocal() as session:
                    result = await session.execute(text("SELECT COUNT(*) FROM dlq"))
                    dlq_count = result.scalar_one() or 0
                
                if dlq_count > 0:
                    logger.info(f"DLQ has {dlq_count} messages, attempting automated replay of {AUTO_REPLAY_BATCH_SIZE}")
                    
                    # Import and run the replay function - USE DEDICATED REPLAY LOGIC
                    try:
                        from db.replay_dlq import replay
                        
                        # Record replay attempt metrics (separate from ingress)
                        from app.metrics import ROUTER_REPLAY_RUNS_TOTAL
                        ROUTER_REPLAY_RUNS_TOTAL.labels(mode="automated").inc()
                        
                        # Replay a batch of messages using DIRECT replay (not main route function)
                        await replay(AUTO_REPLAY_BATCH_SIZE, dry_run=False)
                        logger.info(f"Automated DLQ replay: attempted to process {AUTO_REPLAY_BATCH_SIZE} messages")
                            
                    except Exception as replay_error:
                        logger.error(f"Automated DLQ replay failed: {replay_error}")
                else:
                    logger.debug("DLQ is empty, no automated replay needed")
            else:
                logger.warning("Agents are unhealthy, skipping automated DLQ replay")
                
        except Exception as e:
            logger.error(f"Error in automated DLQ replay task: {e}")
        
        # Wait for the configured interval before next check
        await asyncio.sleep(AUTO_REPLAY_INTERVAL)

# Dependency for API key validation
def require_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# Dependency for rate limiting
async def check_rate_limit(request: Request):
    # Extract sender_id from request if possible
    sender_id = "unknown"
    
    if request.method == "POST" and request.url.path == "/route":
        try:
            body = await request.json()
            sender_id = body.get("sender_id", "unknown")
        except:
            pass
    
    # Check rate limit
    if not await rate_limiter.check_rate_limit(sender_id):
        logger.warning("Rate limit exceeded", sender_id=sender_id)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    return True

# Enhanced health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    start_time = time.time()
    health_data = {"status": "ok", "components": {}, "latency_ms": 0}
    
    try:
        # Check database connection
        await db.execute(text("SELECT 1"))
        health_data["components"]["database"] = {"status": "ok"}
    except Exception as e:
        health_data["status"] = "error"
        health_data["components"]["database"] = {"status": "error", "detail": str(e)}

    # Check agent availability (mock)
    for agent in ["Axis", "M"]:
        health_data["components"][f"agent_{agent}"] = {"status": "ok"}
    
    # Record latency
    health_data["latency_ms"] = round((time.time() - start_time) * 1000, 2)
    
    if health_data["status"] == "error":
        return JSONResponse(status_code=500, content=health_data)
    return health_data

# Main routing endpoint with async processing
@app.post("/route", response_model=RouteResponse, dependencies=[Depends(require_api_key), Depends(check_rate_limit)])
async def route(req: RouteRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Start timing the operation
    with timer(operation="total_route", kind=req.kind or req.type or "unknown"):
        # Generate essential data
        ts = req.ts or now_iso()
        trace_id = new_trace_id()
        
        # Extract payload for classification (everything except metadata fields)
        classification_payload = req.model_dump(exclude={
            'tenant_id', 'event_id', 'user_id', 'payload_version', 
            'type', 'ts', 'kind'
        })
        
        # Generate canonical message_id
        message_id = generate_canonical_message_id(
            tenant_id=req.tenant_id,
            event_id=req.event_id,
            user_id=req.user_id,
            ts_iso=ts,
            payload_version=req.payload_version,
            payload=classification_payload
        )
        
        # Check for duplicates (idempotency)
        existing = await check_message_duplicate(db, message_id)
        if existing:
            logger.info("Duplicate request detected", 
                       message_id=message_id, 
                       trace_id=trace_id,
                       tenant_id=req.tenant_id)
            # Record duplicate metric
            from app.metrics import ROUTER_REJECTED_TOTAL
            ROUTER_REJECTED_TOTAL.labels(reason="duplicate").inc()
            
            return RouteResponse(
                status="already_processed",
                routed_agents=existing["routed_agents"],
                trace_id=trace_id
            )
        
        # Classify if kind not provided
        if not req.kind:
            kind, confidence = await classify(classification_payload)
        else:
            kind, confidence = req.kind, 1.0
            
        # Prepare payload for routing (include relevant fields)
        routing_payload = {
            "tenant_id": req.tenant_id,
            "user_id": req.user_id,
            "message_id": message_id,
            "ts": ts,
            "type": req.type,
            **classification_payload
        }
        
        # Route to appropriate agents with parallel processing
        routed_agents, response = await route_to_agents(db, message_id, kind, routing_payload, trace_id)
        
        # Attempt to log to database
        try:
            metadata_json = json.dumps({
                "trace_id": trace_id,
                "confidence": confidence,
                "tenant_id": req.tenant_id,
                "payload_version": req.payload_version,
                "event_id": req.event_id,
                "user_id": req.user_id,
                "type": req.type,
                "processing_time_ms": round((time.time() - time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))) * 1000, 2)
            }).replace("'", "''")
            
            routed_agents_json = json.dumps(routed_agents).replace("'", "''")
            response_json = json.dumps(response).replace("'", "''")
            
            # Use user_id for sender_id field in database
            sender_id_for_db = req.user_id or "unknown"
            
            sql = f"""
            INSERT INTO logs (log_id, ts, sender_id, kind, routed_agents, response, metadata)
            VALUES ('{message_id}', '{ts}', '{sender_id_for_db}', '{kind}', 
                    '{routed_agents_json}'::jsonb, 
                    '{response_json}'::jsonb, 
                    '{metadata_json}'::jsonb)
            ON CONFLICT (log_id) DO UPDATE SET 
                response = '{response_json}'::jsonb,
                metadata = logs.metadata || '{metadata_json}'::jsonb
            """
            await db.execute(text(sql))
            await db.commit()
            
            logger.info("Operation logged successfully", log_id=message_id)
            
        except Exception as e:
            logger.error("Failed to log operation to database", log_id=message_id, error=str(e))
            try:
                await db.rollback()
            except:
                pass
            
            # Log to structured logs as fallback
            logger.info(
                "operation_completed_unlogged",
                log_id=message_id,
                user_id=req.user_id,
                kind=kind,
                routed_agents=routed_agents,
                response=response,
                trace_id=trace_id,
                event="logging_fallback"
            )
            response = {**response, "logging_status": "failed"}
        
        return RouteResponse(
            status=response.get("status", "routed"),
            routed_agents=routed_agents,
            trace_id=trace_id
        )

# Enhanced logs API with pagination
@app.get("/logs", response_model=List[LogOut], dependencies=[Depends(require_api_key)])
async def logs(
    sender_id: str = Query(...),
    limit: int = Query(100, ge=1, le=MAX_LOGS_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    # Use string formatting to avoid binding issues
    sql = f"""
        SELECT log_id, ts, sender_id, kind, routed_agents::text, response::text, metadata::text
        FROM logs WHERE sender_id = '{sender_id}'
        ORDER BY ts DESC
        LIMIT {limit} OFFSET {offset}
    """
    result = await db.execute(text(sql))
    
    rows = result.fetchall()
    out = []
    
    for (log_id, ts, sid, kind, ra, resp, meta) in rows:
        out.append({
            "log_id": log_id,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "sender_id": sid,
            "kind": kind,
            "routed_agents": json.loads(ra or "[]"),
            "response": json.loads(resp or "{}"),
            "metadata": json.loads(meta or "{}"),
        })
    
    return out

# Metrics endpoint
@app.get("/metrics")
def metrics():
    return PlainTextResponse("# Prometheus metrics are served at /metrics by instrumentator")

# DLQ manual replay endpoint
@app.post("/dlq/replay", dependencies=[Depends(require_api_key)])
async def manual_dlq_replay(
    limit: int = Query(50, ge=1, le=500, description="Number of messages to replay"),
    dry_run: bool = Query(False, description="Preview without actually replaying")
):
    """Manually trigger DLQ replay"""
    try:
        from db.replay_dlq import replay
        
        logger.info(f"Manual DLQ replay triggered: limit={limit}, dry_run={dry_run}")
        
        if dry_run:
            # For dry run, we'd need to modify the replay function to return preview data
            await replay(limit, dry_run=True)
            return {"status": "preview_completed", "limit": limit, "dry_run": True}
        else:
            # Check agents health first
            agents_healthy = await check_agents_health()
            if not agents_healthy:
                logger.warning("Manual DLQ replay: agents appear unhealthy")
                return {
                    "status": "warning", 
                    "message": "Agents appear unhealthy, but proceeding with manual replay",
                    "limit": limit,
                    "agents_healthy": False
                }
            
            await replay(limit, dry_run=False)
            return {
                "status": "completed", 
                "limit": limit, 
                "message": f"Attempted to replay {limit} messages",
                "agents_healthy": True
            }
            
    except Exception as e:
        logger.error(f"Manual DLQ replay failed: {e}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")

# DLQ status endpoint
@app.get("/dlq/status", dependencies=[Depends(require_api_key)])
async def dlq_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT COUNT(*) as count, 
               MIN(ts) as oldest, 
               MAX(attempts) as max_attempts,
               COUNT(DISTINCT log_id) as unique_logs
        FROM dlq
    """))
    
    row = result.fetchone()
    if not row:
        return {"count": 0}
    
    count, oldest, max_attempts, unique_logs = row
    
    # Get reason distribution
    result = await db.execute(text("""
        SELECT reason, COUNT(*) as count
        FROM dlq
        GROUP BY reason
        ORDER BY count DESC
    """))
    
    reasons = [{"reason": r, "count": c} for r, c in result.fetchall()]
    
    return {
        "count": count,
        "oldest": oldest.isoformat() if oldest else None,
        "max_attempts": max_attempts,
        "unique_logs": unique_logs,
        "reasons": reasons
    }
