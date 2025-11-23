"""
Unit tests for idempotency logic
Tests canonical message_id generation and duplicate detection per PR 2
"""
import pytest
import json
from app.router import generate_canonical_message_id, now_iso, check_message_duplicate

class TestCanonicalMessageId:
    """Test canonical message_id generation per PR 2 requirements"""
    
    def test_canonical_message_id_with_event_id(self):
        """Test canonical message_id generation with event_id"""
        tenant_id = "tenant1"
        event_id = "evt_123"
        payload = {"message": "test message", "data": "value"}
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        message_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload)
        message_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload)
        
        assert message_id1 == message_id2
        assert len(message_id1) == 32  # 32 character hash
    
    def test_canonical_message_id_with_user_id_timestamp(self):
        """Test canonical message_id generation with user_id+timestamp"""
        tenant_id = "tenant1"
        user_id = "user123"
        payload = {"message": "test message"}
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        message_id1 = generate_canonical_message_id(tenant_id, None, user_id, ts_iso, payload_version, payload)
        message_id2 = generate_canonical_message_id(tenant_id, None, user_id, ts_iso, payload_version, payload)
        
        assert message_id1 == message_id2
        assert len(message_id1) == 32
    
    def test_canonical_message_id_removes_volatile_fields(self):
        """Test that volatile fields are removed from canonical payload"""
        tenant_id = "tenant1"
        event_id = "evt_123"
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        # Payloads with and without volatile fields should produce same message_id
        payload1 = {"message": "test", "data": "value"}
        payload2 = {"message": "test", "data": "value", "trace_id": "abc123", "timestamp": "2025-09-21T13:00:00Z"}
        
        message_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload1)
        message_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload2)
        
        assert message_id1 == message_id2
    
    def test_canonical_message_id_different_payload_versions(self):
        """Test that different payload versions produce different message_ids"""
        tenant_id = "tenant1"
        event_id = "evt_123"
        payload = {"message": "test"}
        ts_iso = "2025-09-21T12:00:00Z"
        
        message_id_v1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, 1, payload)
        message_id_v2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, 2, payload)
        
        assert message_id_v1 != message_id_v2
    
    def test_canonical_message_id_different_tenants(self):
        """Test that different tenants produce different message_ids"""
        event_id = "evt_123"
        payload = {"message": "test"}
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        message_id1 = generate_canonical_message_id("tenant1", event_id, None, ts_iso, payload_version, payload)
        message_id2 = generate_canonical_message_id("tenant2", event_id, None, ts_iso, payload_version, payload)
        
        assert message_id1 != message_id2
    
    def test_canonical_message_id_payload_order_independence(self):
        """Test that payload key order doesn't affect message_id"""
        tenant_id = "tenant1"
        event_id = "evt_123" 
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}
        
        message_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload1)
        message_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload2)
        
        assert message_id1 == message_id2
    
    def test_canonical_message_id_fallback_to_payload_hash(self):
        """Test fallback when neither event_id nor user_id is provided"""
        tenant_id = "tenant1"
        payload = {"message": "test"}
        payload_version = 1
        ts_iso = "2025-09-21T12:00:00Z"
        
        message_id = generate_canonical_message_id(tenant_id, None, None, ts_iso, payload_version, payload)
        
        assert message_id is not None
        assert len(message_id) == 32

class TestDuplicateDetection:
    """Test duplicate detection functionality"""
    
    @pytest.mark.asyncio
    async def test_check_message_duplicate_not_found(self, db_session):
        """Test duplicate check when message doesn't exist"""
        message_id = "nonexistent_message_id"
        
        result = await check_message_duplicate(db_session, message_id)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_check_message_duplicate_handles_db_error(self, db_session):
        """Test duplicate check handles database errors gracefully"""
        # Test with invalid message_id that might cause DB error
        message_id = "'; DROP TABLE logs; --"
        
        result = await check_message_duplicate(db_session, message_id)
        
        # Should return None on error, not raise exception
        assert result is None
