"""
Unit tests for idempotency logic
Tests deterministic log_id generation and duplicate detection
"""
import pytest
import json
from app.router import deterministic_log_id, now_iso

class TestIdempotency:
    """Test idempotency logic"""
    
    def test_deterministic_log_id_consistency(self):
        """Test that same inputs always produce same log_id"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        payload = {"message": "test message"}
        
        # Generate log_id multiple times with same inputs
        log_id1 = deterministic_log_id(sender_id, timestamp, payload)
        log_id2 = deterministic_log_id(sender_id, timestamp, payload)
        log_id3 = deterministic_log_id(sender_id, timestamp, payload)
        
        assert log_id1 == log_id2 == log_id3
        assert log_id1 is not None
        assert len(log_id1) > 0
    
    def test_deterministic_log_id_format(self):
        """Test log_id format: sender_id:timestamp:hash"""
        sender_id = "user123"
        timestamp = "2025-08-29T12:00:00Z"
        payload = {"message": "hello world"}
        
        log_id = deterministic_log_id(sender_id, timestamp, payload)
        
        # Format is sender_id:timestamp:hash, but timestamp has colons too
        # So we check start and end
        assert log_id.startswith(sender_id + ":")
        assert log_id.endswith(":") == False  # Ends with hash, not colon
        
        # Split by : and check we have the right parts
        parts = log_id.split(":")
        assert parts[0] == sender_id
        assert parts[-1] and len(parts[-1]) == 16  # Hash should be 16 characters
        
        # Reconstruct timestamp from middle parts
        timestamp_parts = parts[1:-1]
        reconstructed_timestamp = ":".join(timestamp_parts)
        assert reconstructed_timestamp == timestamp
    
    def test_different_inputs_different_log_ids(self):
        """Test that different inputs produce different log_ids"""
        base_timestamp = "2025-08-29T12:00:00Z"
        base_payload = {"message": "test"}
        
        # Different sender_ids
        log_id1 = deterministic_log_id("user1", base_timestamp, base_payload)
        log_id2 = deterministic_log_id("user2", base_timestamp, base_payload)
        assert log_id1 != log_id2
        
        # Different timestamps
        log_id3 = deterministic_log_id("user1", "2025-08-29T12:01:00Z", base_payload)
        assert log_id1 != log_id3
        
        # Different payloads
        log_id4 = deterministic_log_id("user1", base_timestamp, {"message": "different"})
        assert log_id1 != log_id4
    
    def test_payload_order_independence(self):
        """Test that payload key order doesn't affect log_id"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}
        payload3 = {"b": 2, "c": 3, "a": 1}
        
        log_id1 = deterministic_log_id(sender_id, timestamp, payload1)
        log_id2 = deterministic_log_id(sender_id, timestamp, payload2)
        log_id3 = deterministic_log_id(sender_id, timestamp, payload3)
        
        assert log_id1 == log_id2 == log_id3
    
    def test_nested_payload_consistency(self):
        """Test consistency with nested payloads"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        
        payload = {
            "user": {"id": 123, "name": "John"},
            "request": {"type": "emergency", "details": ["urgent", "help"]}
        }
        
        log_id1 = deterministic_log_id(sender_id, timestamp, payload)
        log_id2 = deterministic_log_id(sender_id, timestamp, payload)
        
        assert log_id1 == log_id2
    
    def test_special_characters_in_payload(self):
        """Test log_id generation with special characters"""
        sender_id = "user_123"
        timestamp = "2025-08-29T12:00:00Z"
        
        payload = {
            "message": "Hello! @#$%^&*()_+ 🚨 Unicode test",
            "special": "quotes 'single' \"double\" and \n newlines"
        }
        
        log_id = deterministic_log_id(sender_id, timestamp, payload)
        
        assert log_id is not None
        assert ":" in log_id
        # Check that we have sender, timestamp, and hash parts
        parts = log_id.split(":")
        assert len(parts) >= 3  # At least sender:time_part1:time_part2:hash
        assert parts[0] == sender_id
        assert parts[-1] and len(parts[-1]) == 16  # Hash is 16 chars
    
    def test_empty_payload_handling(self):
        """Test log_id generation with empty payload"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        
        log_id1 = deterministic_log_id(sender_id, timestamp, {})
        log_id2 = deterministic_log_id(sender_id, timestamp, {})
        
        assert log_id1 == log_id2
        assert log_id1 is not None
    
    def test_large_payload_handling(self):
        """Test log_id generation with large payloads"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        
        # Create large payload
        large_payload = {
            "data": "x" * 10000,  # 10KB of data
            "items": list(range(1000)),
            "metadata": {"key" + str(i): "value" + str(i) for i in range(100)}
        }
        
        log_id = deterministic_log_id(sender_id, timestamp, large_payload)
        
        assert log_id is not None
        parts = log_id.split(":")
        assert len(parts[-1]) == 16  # Hash should still be 16 chars
    
    def test_now_iso_format(self):
        """Test that now_iso returns valid ISO format"""
        timestamp = now_iso()
        
        # Should be in format: YYYY-MM-DDTHH:MM:SSZ
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        assert len(timestamp) == 20  # 2025-08-29T12:00:00Z
    
    def test_unicode_payload_handling(self):
        """Test log_id generation with Unicode characters"""
        sender_id = "test_user"
        timestamp = "2025-08-29T12:00:00Z"
        
        payload = {
            "message": "Hello 世界 🌍 emoji test",
            "unicode": "áéíóú çñü αβγ δεζ"
        }
        
        log_id1 = deterministic_log_id(sender_id, timestamp, payload)
        log_id2 = deterministic_log_id(sender_id, timestamp, payload)
        
        assert log_id1 == log_id2
        assert log_id1 is not None
