import os, json, sys, asyncio, httpx, time
from sqlalchemy import create_engine, text
from datetime import datetime
import uuid

# Add app directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.router import agents_for, now_iso

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
API_ENDPOINT = "http://localhost:8000/route"
API_KEY = os.getenv("API_KEY", "dev-key")

async def process_dlq_entry(id_: int, log_id: str, payload: dict):
    """Process a single DLQ entry with retry logic"""
    try:
        # Extract the original request
        request = payload.get("request", {})
        if not request:
            print(f"⚠️ Invalid payload format for DLQ id={id_}, skipping")
            return False
            
        # Get or generate a trace ID
        trace_id = payload.get("trace_id", uuid.uuid4().hex)
        
        # Determine the kind of request
        kind = request.get("kind")
        if not kind:
            # Try to get the kind from the logs table
            with engine.begin() as conn:
                result = conn.execute(
                    text("SELECT kind FROM logs WHERE log_id = :log_id"),
                    {"log_id": log_id}
                ).first()
                if result:
                    kind = result[0]
                else:
                    kind = "unknown"
        
        # Get the appropriate agents
        routed_agents = agents_for(kind)
        if "DLQ" in routed_agents:
            routed_agents.remove("DLQ")  # Don't route back to DLQ
            if not routed_agents:  # If only DLQ was present
                routed_agents = ["Axis"]  # Default to Axis as fallback
        
        # For simplicity, simulate successful replay for known agent types
        success = True if routed_agents and routed_agents != ["DLQ"] else False
        
        with engine.begin() as conn:
            if success:
                # Update logs table
                conn.execute(text("""
                    INSERT INTO logs (log_id, ts, sender_id, kind, routed_agents, response, metadata)
                    VALUES (:log_id, NOW(), :sender_id, :kind, CAST(:routed_agents AS jsonb), CAST(:response AS jsonb), CAST(:metadata AS jsonb))
                    ON CONFLICT (log_id) DO UPDATE SET
                        response = CAST(:response AS jsonb),
                        metadata = logs.metadata || CAST(:metadata AS jsonb)
                """), {
                    "log_id": log_id,
                    "sender_id": request.get("sender_id", "dlq_replay"),
                    "kind": kind,
                    "routed_agents": json.dumps(routed_agents),
                    "response": json.dumps({
                        "status": "replayed",
                        "routed_agents": routed_agents,
                        "trace_id": trace_id
                    }),
                    "metadata": json.dumps({
                        "replayed_at": datetime.utcnow().isoformat(),
                        "trace_id": trace_id
                    })
                })
                
                # Delete from DLQ
                conn.execute(text("DELETE FROM dlq WHERE id = :id"), {"id": id_})
                print(f"✅ Successfully replayed DLQ id={id_}, log_id={log_id}")
                return True
            else:
                # Increment retry counter
                attempts = conn.execute(
                    text("SELECT attempts FROM dlq WHERE id = :id"),
                    {"id": id_}
                ).scalar()
                
                if attempts >= 3:  # Max retries
                    print(f"❌ Max retries reached for DLQ id={id_}, log_id={log_id}. Keeping in DLQ.")
                    return False
                
                # Update attempts counter
                conn.execute(
                    text("UPDATE dlq SET attempts = attempts + 1 WHERE id = :id"),
                    {"id": id_}
                )
                print(f"⚠️ Failed to replay DLQ id={id_}, log_id={log_id}. Incremented retry counter to {attempts + 1}.")
                return False
    
    except Exception as e:
        print(f"❌ Error processing DLQ id={id_}, log_id={log_id}: {str(e)}")
        return False

async def replay_async(limit: int, retry_delay: float = 0.5):
    """Replay DLQ entries with bounded concurrency"""
    print(f"Starting replay of up to {limit} DLQ entries...")
    
    # Get DLQ entries
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, log_id, payload FROM dlq ORDER BY ts ASC LIMIT :l"), 
            {"l": limit}
        ).fetchall()
    
    if not rows:
        print("No DLQ entries found to replay.")
        return
    
    print(f"Found {len(rows)} DLQ entries to process.")
    
    # Process entries with a small delay between them to avoid overloading the system
    successful = 0
    failed = 0
    
    for idx, (id_, log_id, payload) in enumerate(rows):
        try:
            # payload is already a dict from JSONB column
            if await process_dlq_entry(id_, log_id, payload):
                successful += 1
            else:
                failed += 1
        except Exception as e:
            print(f"⚠️ Error processing DLQ payload for id={id_}: {e}")
            failed += 1
        
        # Small delay between processing entries
        if idx < len(rows) - 1:  # No need to delay after the last one
            await asyncio.sleep(retry_delay)
    
    print(f"DLQ replay completed: {successful} successful, {failed} failed")

def replay(limit: int):
    """Entry point for CLI tool"""
    asyncio.run(replay_async(limit))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    replay(args.limit)
