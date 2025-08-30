"""
Pytest configuration and shared fixtures
"""
import pytest
import pytest_asyncio
import asyncio
import os
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.main import app
from app.db import AsyncSessionLocal
from app.models import Base

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/routerdb_test"
)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine):
    """Create a real database session for testing using Docker PostgreSQL"""
    AsyncTestSessionLocal = sessionmaker(
        bind=test_engine, 
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False, 
        autoflush=False
    )
    
    session = AsyncTestSessionLocal()
    try:
        yield session
    finally:
        # Clean up after each test
        await session.rollback()
        await session.close()

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_agent_responses():
    """Mock responses for agent calls"""
    return {
        "Axis": {"status": "success", "agent": "Axis", "result": "Processed"},
        "M": {"status": "success", "agent": "M", "result": "Policy checked"},
        "error": {"status": "error", "message": "Agent failed"}
    }

@pytest.fixture
def sample_payloads():
    """Sample payloads for testing classification"""
    return {
        "emergency": {
            "message": "urgent emergency situation requiring immediate assistance",
            "priority": "high"
        },
        "policy": {
            "message": "what is the GDPR compliance policy for data processing",
            "type": "policy_inquiry"
        },
        "assist": {
            "message": "help me understand how this feature works",
            "category": "support"
        },
        "unknown": {
            "message": "random message with no clear category",
            "data": "miscellaneous"
        }
    }

@pytest.fixture
def mock_trace_id():
    """Mock trace ID for testing"""
    return "test-trace-id-12345"
