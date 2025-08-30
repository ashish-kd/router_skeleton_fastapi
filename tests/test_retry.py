"""
Unit tests for retry mechanism
Tests retry logic with exponential backoff
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from tenacity import RetryError
from app.utils import with_retry, circuit_breaker, CircuitBreaker

class TestRetryMechanism:
    """Test retry logic and circuit breaker"""
    
    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """Test successful call on first attempt requires no retry"""
        call_count = 0
        
        @with_retry(max_attempts=3)
        async def successful_func(agent="test"):
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await successful_func()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self):
        """Test retry mechanism when function fails then succeeds"""
        call_count = 0
        
        @with_retry(max_attempts=3)
        async def flaky_func(agent="test"):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = await flaky_func()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test behavior when all retry attempts are exhausted"""
        call_count = 0
        
        @with_retry(max_attempts=2)
        async def always_fails(agent="test"):
            nonlocal call_count
            call_count += 1
            raise Exception("Always fails")
        
        with pytest.raises(Exception, match="Always fails"):
            await always_fails()
        
        assert call_count == 2  # Called twice (original + 1 retry)
    
    @pytest.mark.asyncio
    async def test_retry_with_different_exceptions(self):
        """Test retry with different types of exceptions"""
        @with_retry(max_attempts=2)
        async def raises_different_errors(agent="test", error_type="generic"):
            if error_type == "timeout":
                raise asyncio.TimeoutError("Request timeout")
            elif error_type == "connection":
                raise ConnectionError("Connection failed")
            else:
                raise ValueError("Invalid value")
        
        # All should be retried
        with pytest.raises(asyncio.TimeoutError):
            await raises_different_errors(error_type="timeout")
        
        with pytest.raises(ConnectionError):
            await raises_different_errors(error_type="connection")
        
        with pytest.raises(ValueError):
            await raises_different_errors(error_type="value")

class TestCircuitBreaker:
    """Test circuit breaker functionality"""
    
    def setup_method(self):
        """Reset circuit breaker for each test"""
        self.cb = CircuitBreaker(failure_threshold=3, recovery_time=1)
    
    def test_circuit_initially_closed(self):
        """Test circuit breaker starts in closed state"""
        assert not self.cb.is_circuit_open("test_agent")
    
    def test_circuit_opens_after_threshold_failures(self):
        """Test circuit opens after failure threshold is reached"""
        agent = "test_agent"
        
        # Record failures up to threshold
        for i in range(2):
            result = self.cb.record_failure(agent)
            assert result is False  # Circuit not opened yet
            assert not self.cb.is_circuit_open(agent)
        
        # Third failure should open circuit
        result = self.cb.record_failure(agent)
        assert result is True  # Circuit was opened
        assert self.cb.is_circuit_open(agent)
    
    def test_circuit_success_resets_counter(self):
        """Test successful calls reset failure counter"""
        agent = "test_agent"
        
        # Record some failures
        self.cb.record_failure(agent)
        self.cb.record_failure(agent)
        assert not self.cb.is_circuit_open(agent)
        
        # Success should reset counter
        self.cb.record_success(agent)
        
        # Should take 3 more failures to open circuit
        self.cb.record_failure(agent)
        self.cb.record_failure(agent)
        assert not self.cb.is_circuit_open(agent)
        
        self.cb.record_failure(agent)
        assert self.cb.is_circuit_open(agent)
    
    @pytest.mark.asyncio
    async def test_circuit_closes_after_recovery_time(self):
        """Test circuit closes after recovery time"""
        agent = "test_agent"
        
        # Open the circuit
        for _ in range(3):
            self.cb.record_failure(agent)
        assert self.cb.is_circuit_open(agent)
        
        # Wait for recovery time (1 second)
        await asyncio.sleep(1.1)
        
        # Circuit should be closed now
        assert not self.cb.is_circuit_open(agent)
    
    def test_multiple_agents_independent(self):
        """Test that different agents have independent circuit states"""
        agent1 = "agent_1"
        agent2 = "agent_2"
        
        # Fail agent1 to threshold
        for _ in range(3):
            self.cb.record_failure(agent1)
        
        assert self.cb.is_circuit_open(agent1)
        assert not self.cb.is_circuit_open(agent2)  # agent2 should be unaffected
    
    def test_failure_count_tracking(self):
        """Test that failure counts are tracked correctly"""
        agent = "test_agent"
        
        # Initially no failures
        assert agent not in self.cb.failure_counts
        
        # Record failures
        self.cb.record_failure(agent)
        assert self.cb.failure_counts[agent] == 1
        
        self.cb.record_failure(agent)
        assert self.cb.failure_counts[agent] == 2
        
        # Success resets
        self.cb.record_success(agent)
        assert self.cb.failure_counts[agent] == 0

class TestIntegratedRetryAndCircuitBreaker:
    """Test retry mechanism integrated with circuit breaker"""
    
    def setup_method(self):
        """Setup for each test"""
        # Reset global circuit breaker
        circuit_breaker.failure_counts.clear()
        circuit_breaker.circuit_open_until.clear()
    
    @pytest.mark.asyncio
    async def test_retry_respects_circuit_breaker(self):
        """Test that retry mechanism respects circuit breaker state"""
        agent = "test_agent"
        
        # Open circuit by recording failures directly
        for _ in range(5):  # More than threshold
            circuit_breaker.record_failure(agent)
        
        @with_retry(max_attempts=3)
        async def circuit_aware_func(agent=agent):
            if circuit_breaker.is_circuit_open(agent):
                raise Exception(f"Circuit open for agent {agent}")
            return "success"
        
        # Should fail immediately due to open circuit
        with pytest.raises(Exception, match="Circuit open"):
            await circuit_aware_func()
    
    @pytest.mark.asyncio 
    async def test_metrics_updated_during_retry(self):
        """Test that metrics are updated during retry attempts"""
        with patch('app.utils.RETRY_ATTEMPTS') as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            
            @with_retry(max_attempts=2)
            async def failing_func(agent="test"):
                raise Exception("Always fails")
            
            with pytest.raises(Exception):
                await failing_func()
            
            # Verify metrics were called
            assert mock_metric.labels.called
            assert mock_metric.labels.return_value.inc.called
