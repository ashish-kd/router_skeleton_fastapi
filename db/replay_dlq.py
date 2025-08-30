import os
import json
import asyncio
import time
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dlq_replay")

# Get database URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/routerdb")
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2", "postgresql+asyncpg")

# Create async engine
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    echo=False,
)

AsyncSessionLocal = sessionmaker(
    bind=async_engine, 
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False, 
    autoflush=False
)

async def get_db():
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def replay_item(db: AsyncSession, id_: int, log_id: str, payload_text: str):
    """Replay a single DLQ item with error handling"""
    try:
        # Parse the payload
        payload = json.loads(payload_text)
        sender_id = payload.get("sender_id", "unknown")
        
        # Determine what kind of message it is (simplified classification)
        kind = "assist"  # Default
        if isinstance(payload.get("payload"), dict):
            msg = json.dumps(payload.get("payload", {})).lower()
            if any(k in msg for k in ["emergency", "urgent", "crisis"]):
                kind = "emergency"
            elif any(k in msg for k in ["policy", "compliance"]):
                kind = "policy"
        
        # Insert into logs table using f-string to avoid parameter binding issues
        routed_agents_json = json.dumps(["Axis"]).replace("'", "''")
        response_json = json.dumps({"status": "replayed", "source": "dlq_replay"}).replace("'", "''")
        metadata_json = json.dumps({
            "replayed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "original_dlq_id": id_
        }).replace("'", "''")
        
        sql = f"""
            INSERT INTO logs (log_id, sender_id, kind, routed_agents, response, metadata)
            VALUES ('{log_id}', '{sender_id}', '{kind}', '{routed_agents_json}'::jsonb, '{response_json}'::jsonb, '{metadata_json}'::jsonb)
            ON CONFLICT (log_id) DO UPDATE SET 
                response = '{response_json}'::jsonb,
                metadata = logs.metadata || '{metadata_json}'::jsonb
        """
        await db.execute(text(sql))
        
        # Delete from DLQ
        await db.execute(text(f"DELETE FROM dlq WHERE id = {id_}"))
        await db.commit()
        logger.info(f"Successfully replayed DLQ item id={id_}, log_id={log_id}")
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Error replaying DLQ item id={id_}: {str(e)}")
        
        # Update attempts count
        try:
            await db.execute(text(f"UPDATE dlq SET attempts = attempts + 1 WHERE id = {id_}"))
            await db.commit()
        except Exception:
            pass
            
        return False

async def replay(limit: int, dry_run: bool = False):
    """Replay DLQ items up to the limit"""
    start_time = time.time()
    success_count = 0
    error_count = 0
    
    logger.info(f"Starting DLQ replay with limit={limit}, dry_run={dry_run}")
    
    async with AsyncSessionLocal() as db:
        # Get DLQ items to replay
        result = await db.execute(text(f"""
            SELECT id, log_id, payload::text 
            FROM dlq 
            ORDER BY ts ASC, attempts ASC
            LIMIT {limit}
        """))
        
        rows = result.fetchall()
        total = len(rows)
        
        if total == 0:
            logger.info("No DLQ items to replay")
            return
            
        logger.info(f"Found {total} DLQ items to replay")
        
        if dry_run:
            for (id_, log_id, payload_text) in rows:
                logger.info(f"Would replay: id={id_}, log_id={log_id}")
            return
            
        # Process each DLQ item
        for (id_, log_id, payload_text) in rows:
            success = await replay_item(db, id_, log_id, payload_text)
            if success:
                success_count += 1
            else:
                error_count += 1
                
    duration = time.time() - start_time
    logger.info(f"DLQ replay complete: processed {total}, success={success_count}, error={error_count}, duration={duration:.2f}s")

async def main():
    """Main function"""
    import argparse
    ap = argparse.ArgumentParser(description='Replay messages from DLQ')
    ap.add_argument("--limit", type=int, default=100, help="Maximum number of items to replay")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be replayed without actually doing it")
    args = ap.parse_args()
    
    await replay(args.limit, args.dry_run)

if __name__ == "__main__":
    asyncio.run(main())
