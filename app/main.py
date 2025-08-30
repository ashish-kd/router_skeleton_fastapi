import os, json, time
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.metrics import instrumentator, setup_metrics, signals_received_total, router_latency_seconds, dlq_total
from app.schemas import RouteRequest, RouteResponse, LogOut
from app.router import classify, agents_for, deterministic_log_id, now_iso, new_trace_id

API_KEY = os.getenv("API_KEY", "dev-key")

# Setup metrics
setup_metrics()

app = FastAPI(title="Router Service", version="0.1.0")

# Instrument app for Prometheus metrics (must be before startup)
instrumentator.instrument(app).expose(app)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})

@app.post("/route", response_model=RouteResponse, dependencies=[Depends(require_api_key)])
async def route(req: RouteRequest, db: Session = Depends(get_db)):
    start_time = time.time()
    
    # Core routing logic
    ts = req.timestamp or now_iso()
    if req.kind:
        kind, confidence = req.kind, 1.0
    else:
        kind, confidence = classify(req.payload)
    log_id = req.log_id or deterministic_log_id(req.sender_id, ts, req.payload)
    trace_id = new_trace_id()
    
    # Check for idempotency
    existing = db.execute(
        text("SELECT log_id, response FROM logs WHERE log_id = :log_id"),
        {"log_id": log_id}
    ).first()
    
    if existing:
        # Return cached response for idempotency
        response_data = json.loads(existing[1]) if isinstance(existing[1], str) else existing[1]
        return RouteResponse(
            status=response_data.get("status", "duplicate"),
            routed_agents=response_data.get("routed_agents", []),
            trace_id=trace_id
        )
    
    # Get agents and simulate routing
    routed_agents = agents_for(kind)
    
    if kind != "unknown" and routed_agents != ["DLQ"]:
        # Handle fan-out for multi-agent requests (e.g., emergency → [M, Axis])
        if len(routed_agents) > 1:
            # Async fan-out with bounded parallelism
            import asyncio
            successful_agents = []
            
            async def try_agent(agent):
                return agent if agent == "M" else (agent if hash(log_id + agent) % 3 != 0 else None)
            
            # Execute all agents concurrently with bounded parallelism
            tasks = [try_agent(agent) for agent in routed_agents]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_agents = [r for r in results if r and not isinstance(r, Exception)]
            
            if successful_agents:
                response_data = {"status": "success", "routed_agents": successful_agents, "trace_id": trace_id}
                status = "routed"
            else:
                # All agents failed - route to DLQ
                dlq_total.labels(reason="all_agents_failed").inc()
                db.execute(text("""
                    INSERT INTO dlq (log_id, reason, payload, attempts)
                    VALUES (:log_id, :reason, CAST(:payload AS jsonb), :attempts)
                """), {
                    "log_id": log_id,
                    "reason": "All agents failed",
                    "payload": json.dumps({"request": req.dict(), "trace_id": trace_id}),
                    "attempts": 0
                })
                status = "dlq"
                response_data = {"status": "dlq", "reason": "all_agents_failed", "trace_id": trace_id}
        else:
            # Single agent - simple sync handling
            response_data = {"status": "success", "routed_agents": routed_agents, "trace_id": trace_id}
            status = "routed"
    else:
        # Unknown type goes to DLQ
        dlq_total.labels(reason="unknown_kind").inc()
        db.execute(text("""
            INSERT INTO dlq (log_id, reason, payload, attempts)
            VALUES (:log_id, :reason, CAST(:payload AS jsonb), :attempts)
        """), {
            "log_id": log_id,
            "reason": f"Unknown request kind: {kind}",
            "payload": json.dumps({"request": req.dict(), "trace_id": trace_id}),
            "attempts": 0
        })
        response_data = {"status": "dlq", "reason": "unknown_kind", "trace_id": trace_id}
        status = "dlq"
    
    # Log to database
    process_time = time.time() - start_time
    db.execute(text("""
        INSERT INTO logs (log_id, ts, sender_id, kind, routed_agents, response, metadata)
        VALUES (:log_id, :ts, :sender_id, :kind, CAST(:routed_agents AS jsonb), CAST(:response AS jsonb), CAST(:metadata AS jsonb))
        ON CONFLICT (log_id) DO UPDATE SET
            response = CAST(:response AS jsonb),
            metadata = logs.metadata || CAST(:metadata AS jsonb)
    """), {
        "log_id": log_id,
        "ts": ts,
        "sender_id": req.sender_id,
        "kind": kind,
        "routed_agents": json.dumps(response_data.get("routed_agents", []) if status == "routed" else []),
        "response": json.dumps(response_data),
        "metadata": json.dumps({"trace_id": trace_id, "confidence": confidence, "processing_time_ms": round(process_time * 1000, 2)})
    })
    db.commit()
    
    # Record metrics
    signals_received_total.labels(kind=kind).inc()
    router_latency_seconds.labels(kind=kind).observe(process_time)
    
    return RouteResponse(
        status=status,
        routed_agents=response_data.get("routed_agents", []) if status == "routed" else [],
        trace_id=trace_id
    )

@app.get("/logs", response_model=list[LogOut], dependencies=[Depends(require_api_key)])
def logs(sender_id: str = Query(...), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT log_id, ts, sender_id, kind, routed_agents, response, metadata
        FROM logs WHERE sender_id = :sid ORDER BY ts DESC LIMIT 100
    """), {"sid": sender_id}).fetchall()
    out = []
    for (log_id, ts, sid, kind, ra, resp, meta) in rows:
        out.append({
            "log_id": log_id,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "sender_id": sid,
            "kind": kind,
            "routed_agents": json.loads(ra) if isinstance(ra, str) else (ra or []),
            "response": json.loads(resp) if isinstance(resp, str) else (resp or {}),
            "metadata": json.loads(meta) if isinstance(meta, str) else (meta or {}),
        })
    return out

@app.get("/metrics")
def metrics():
    return PlainTextResponse("# Prometheus metrics are served at /metrics by instrumentator")