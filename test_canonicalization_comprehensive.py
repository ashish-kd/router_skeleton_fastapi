#!/usr/bin/env python3
"""
Comprehensive Canonicalization Test Suite
Tests both unit-level canonicalization and end-to-end API behavior
Validates that key order variance doesn't change hash generation
"""

import requests
import json
import hashlib
import sys
from typing import Dict, Any
from datetime import datetime

# Import the function directly for unit testing
try:
    from app.router import generate_canonical_message_id
    UNIT_TESTS_AVAILABLE = True
except ImportError:
    print("Warning: Could not import generate_canonical_message_id for unit tests")
    UNIT_TESTS_AVAILABLE = False

API_BASE = "http://localhost:8000"
API_KEY = "dev-key"

class CanonicalzationTester:
    """Comprehensive canonicalization testing class"""
    
    def __init__(self):
        self.test_results = []
        
    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   {details}")
        self.test_results.append((test_name, passed, details))
        
    def test_unit_canonicalization(self):
        """Test canonicalization at the unit level"""
        if not UNIT_TESTS_AVAILABLE:
            self.log_result("Unit Canonicalization Tests", False, "Cannot import function")
            return
            
        print("\n=== Unit Level Canonicalization Tests ===")
        
        # Test 1: Basic key reordering
        tenant_id = "test-tenant"
        event_id = "test-event-123"
        payload_version = 1
        ts_iso = "2025-09-27T12:00:00Z"
        
        payload1 = {"a": 1, "b": 2, "c": 3, "text": "test"}
        payload2 = {"c": 3, "text": "test", "a": 1, "b": 2}
        payload3 = {"b": 2, "c": 3, "text": "test", "a": 1}
        
        id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload1)
        id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload2)
        id3 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, payload3)
        
        self.log_result("Basic Key Reordering", 
                       id1 == id2 == id3, 
                       f"IDs: {id1[:8]}... == {id2[:8]}... == {id3[:8]}...")
        
        # Test 2: Nested object key reordering
        nested_payload1 = {
            "user": {"name": "test", "age": 25, "active": True},
            "settings": {"theme": "dark", "notifications": True, "timeout": 30},
            "tags": ["urgent", "test"]
        }
        
        nested_payload2 = {
            "tags": ["urgent", "test"],
            "user": {"active": True, "name": "test", "age": 25},
            "settings": {"timeout": 30, "theme": "dark", "notifications": True}
        }
        
        nested_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, nested_payload1)
        nested_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, nested_payload2)
        
        self.log_result("Nested Object Key Reordering",
                       nested_id1 == nested_id2,
                       f"Nested IDs: {nested_id1[:8]}... == {nested_id2[:8]}...")
        
        # Test 3: Volatile field removal
        volatile_payload1 = {"message": "test", "data": "value"}
        volatile_payload2 = {"message": "test", "data": "value", "trace_id": "abc123", "timestamp": "2025-09-27T13:00:00Z"}
        
        vol_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, volatile_payload1)
        vol_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, volatile_payload2)
        
        self.log_result("Volatile Field Removal",
                       vol_id1 == vol_id2,
                       f"Volatile IDs: {vol_id1[:8]}... == {vol_id2[:8]}...")
        
        # Test 4: Deep nesting with arrays
        deep_payload1 = {
            "config": {
                "database": {"host": "localhost", "port": 5432, "ssl": True},
                "cache": {"redis": {"host": "redis", "port": 6379}, "ttl": 3600}
            },
            "features": [
                {"name": "auth", "enabled": True, "config": {"timeout": 30}},
                {"name": "logging", "enabled": False, "config": {"level": "info"}}
            ]
        }
        
        deep_payload2 = {
            "features": [
                {"config": {"timeout": 30}, "enabled": True, "name": "auth"},
                {"config": {"level": "info"}, "name": "logging", "enabled": False}
            ],
            "config": {
                "cache": {"ttl": 3600, "redis": {"port": 6379, "host": "redis"}},
                "database": {"ssl": True, "port": 5432, "host": "localhost"}
            }
        }
        
        deep_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, deep_payload1)
        deep_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, deep_payload2)
        
        self.log_result("Deep Nested Canonicalization",
                       deep_id1 == deep_id2,
                       f"Deep IDs: {deep_id1[:8]}... == {deep_id2[:8]}...")
                       
    def test_api_canonicalization(self):
        """Test canonicalization through the API"""
        print("\n=== API Level Canonicalization Tests ===")
        
        # Check baseline metrics
        try:
            metrics_resp = requests.get(f"{API_BASE}/metrics")
            baseline_duplicates = 0
            for line in metrics_resp.text.split('\n'):
                if 'router_rejected_total{reason="duplicate"}' in line:
                    baseline_duplicates = float(line.split()[-1])
                    break
        except:
            baseline_duplicates = 0
            
        # Test 1: Simple API canonicalization
        timestamp = datetime.now().isoformat() + "Z"
        
        simple_payload1 = {
            "tenant_id": "api-canon-test",
            "user_id": "api-user",
            "event_id": f"api-canon-{timestamp}",
            "type": "assist",
            "payload_version": 1,
            "text": "Please help me with this canonicalization test"
        }
        
        simple_payload2 = {
            "text": "Please help me with this canonicalization test",
            "payload_version": 1,
            "event_id": f"api-canon-{timestamp}",
            "user_id": "api-user",
            "tenant_id": "api-canon-test",
            "type": "assist"
        }
        
        resp1 = requests.post(f"{API_BASE}/route", json=simple_payload1, headers={"X-API-Key": API_KEY})
        resp2 = requests.post(f"{API_BASE}/route", json=simple_payload2, headers={"X-API-Key": API_KEY})
        
        api_simple_passed = (
            resp1.status_code == 200 and 
            resp2.status_code == 200 and
            resp1.json().get('status') != 'already_processed' and
            resp2.json().get('status') == 'already_processed'
        )
        
        self.log_result("API Simple Canonicalization",
                       api_simple_passed,
                       f"Resp1: {resp1.json().get('status')}, Resp2: {resp2.json().get('status')}")
        
        # Test 2: Complex nested API canonicalization
        timestamp2 = datetime.now().isoformat() + "Z"
        
        complex_payload1 = {
            "tenant_id": "api-nested-test",
            "user_id": "api-nested-user",
            "event_id": f"api-nested-{timestamp2}",
            "type": "policy",
            "payload_version": 1,
            "text": "Complex nested canonicalization test with compliance keywords",
            "metadata": {
                "priority": "high",
                "source": "api",
                "config": {"timeout": 30, "retries": 3},
                "tags": ["compliance", "test", "nested"],
                "params": {"a": 1, "b": 2, "c": {"x": 10, "y": 20}}
            }
        }
        
        complex_payload2 = {
            "metadata": {
                "tags": ["compliance", "test", "nested"],
                "params": {"c": {"y": 20, "x": 10}, "b": 2, "a": 1},
                "config": {"retries": 3, "timeout": 30},
                "source": "api",
                "priority": "high"
            },
            "text": "Complex nested canonicalization test with compliance keywords",
            "payload_version": 1,
            "event_id": f"api-nested-{timestamp2}",
            "user_id": "api-nested-user",
            "tenant_id": "api-nested-test",
            "type": "policy"
        }
        
        resp3 = requests.post(f"{API_BASE}/route", json=complex_payload1, headers={"X-API-Key": API_KEY})
        resp4 = requests.post(f"{API_BASE}/route", json=complex_payload2, headers={"X-API-Key": API_KEY})
        
        api_complex_passed = (
            resp3.status_code == 200 and 
            resp4.status_code == 200 and
            resp3.json().get('status') != 'already_processed' and
            resp4.json().get('status') == 'already_processed'
        )
        
        self.log_result("API Complex Nested Canonicalization",
                       api_complex_passed,
                       f"Resp3: {resp3.json().get('status')}, Resp4: {resp4.json().get('status')}")
                       
        # Test 3: Volatile field independence via API
        timestamp3 = datetime.now().isoformat() + "Z"
        
        volatile_payload1 = {
            "tenant_id": "api-volatile-test",
            "user_id": "api-volatile-user", 
            "event_id": f"api-volatile-{timestamp3}",
            "type": "assist",
            "payload_version": 1,
            "text": "Volatile field test - help needed"
        }
        
        volatile_payload2 = {
            "tenant_id": "api-volatile-test",
            "user_id": "api-volatile-user",
            "event_id": f"api-volatile-{timestamp3}",
            "type": "assist", 
            "payload_version": 1,
            "text": "Volatile field test - help needed",
            "trace_id": "should-be-ignored",
            "timestamp": "should-be-ignored",
            "ts": "should-also-be-ignored"
        }
        
        resp5 = requests.post(f"{API_BASE}/route", json=volatile_payload1, headers={"X-API-Key": API_KEY})
        resp6 = requests.post(f"{API_BASE}/route", json=volatile_payload2, headers={"X-API-Key": API_KEY})
        
        api_volatile_passed = (
            resp5.status_code == 200 and
            resp6.status_code == 200 and
            resp5.json().get('status') != 'already_processed' and
            resp6.json().get('status') == 'already_processed'
        )
        
        self.log_result("API Volatile Field Independence", 
                       api_volatile_passed,
                       f"Resp5: {resp5.json().get('status')}, Resp6: {resp6.json().get('status')}")
                       
        # Verify metrics incremented correctly
        try:
            final_metrics_resp = requests.get(f"{API_BASE}/metrics")
            final_duplicates = 0
            for line in final_metrics_resp.text.split('\n'):
                if 'router_rejected_total{reason="duplicate"}' in line:
                    final_duplicates = float(line.split()[-1])
                    break
            
            expected_increment = 3  # 3 duplicate requests should have been made
            actual_increment = final_duplicates - baseline_duplicates
            
            metrics_passed = actual_increment == expected_increment
            self.log_result("Duplicate Metrics Incremented",
                           metrics_passed,
                           f"Expected +{expected_increment}, got +{actual_increment}")
                           
        except Exception as e:
            self.log_result("Duplicate Metrics Incremented", False, f"Error checking metrics: {e}")
            
    def test_edge_cases(self):
        """Test edge cases for canonicalization"""
        if not UNIT_TESTS_AVAILABLE:
            return
            
        print("\n=== Edge Case Tests ===")
        
        # Test with empty nested objects
        empty_nested1 = {"data": {}, "items": [], "config": {"nested": {}}}
        empty_nested2 = {"config": {"nested": {}}, "items": [], "data": {}}
        
        tenant_id = "edge-test"
        event_id = "edge-event"
        payload_version = 1
        ts_iso = "2025-09-27T12:00:00Z"
        
        empty_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, empty_nested1)
        empty_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, empty_nested2)
        
        self.log_result("Empty Nested Objects",
                       empty_id1 == empty_id2,
                       f"Empty IDs: {empty_id1[:8]}... == {empty_id2[:8]}...")
        
        # Test with special characters and unicode
        unicode_payload1 = {
            "message": "Test with émojis 🚀 and spëcial chars",
            "data": {"ñame": "tëst", "valué": "spëcial"}
        }
        
        unicode_payload2 = {
            "data": {"valué": "spëcial", "ñame": "tëst"},
            "message": "Test with émojis 🚀 and spëcial chars"
        }
        
        unicode_id1 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, unicode_payload1)
        unicode_id2 = generate_canonical_message_id(tenant_id, event_id, None, ts_iso, payload_version, unicode_payload2)
        
        self.log_result("Unicode and Special Characters",
                       unicode_id1 == unicode_id2,
                       f"Unicode IDs: {unicode_id1[:8]}... == {unicode_id2[:8]}...")
                       
    def run_all_tests(self):
        """Run all canonicalization tests"""
        print("🧪 Comprehensive Canonicalization Test Suite")
        print("=" * 50)
        
        self.test_unit_canonicalization()
        self.test_api_canonicalization() 
        self.test_edge_cases()
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Results Summary")
        print("=" * 50)
        
        passed = sum(1 for _, result, _ in self.test_results if result)
        total = len(self.test_results)
        
        print(f"Passed: {passed}/{total}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("\n🎉 All canonicalization tests PASSED!")
            print("✅ Key order variance doesn't change hash generation")
            print("✅ Nested object canonicalization works correctly")  
            print("✅ Volatile fields are properly excluded")
            print("✅ API-level duplicate detection works")
            return True
        else:
            print(f"\n❌ {total-passed} tests FAILED")
            for name, result, details in self.test_results:
                if not result:
                    print(f"   ❌ {name}: {details}")
            return False

def main():
    """Main test runner"""
    tester = CanonicalzationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()