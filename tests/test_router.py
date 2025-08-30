"""
Unit tests for routing logic
Tests end-to-end routing behavior
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.router import route_to_agents, call_agent, new_trace_id

class TestRouterLogic:
    """Test main routing logic"""
    
    @pytest.mark.asyncio
    async def test_emergency_routes_to_both_agents(self, db_session, mock_trace_id):
        """Test emergency signals route to both M and Axis"""
        payload = {"message": "urgent emergency situation"}
        
        with patch('app.router.call_agent') as mock_call:
            mock_call.return_value = {"status": "success", "agent": "test"}
            
            agents, response = await route_to_agents(
                db_session, 
                "test_log_id", 
                "emergency", 
                payload, 
                mock_trace_id
            )
            
            assert "M" in agents
            assert "Axis" in agents
            assert response["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_policy_routes_to_m_only(self, db_session, mock_trace_id):
        """Test policy signals route to M only"""
        payload = {"message": "GDPR policy question"}
        
        with patch('app.router.call_agent') as mock_call:
            mock_call.return_value = {"status": "success", "agent": "M"}
            
            agents, response = await route_to_agents(
                db_session,
                "test_log_id",
                "policy", 
                payload,
                mock_trace_id
            )
            
            assert agents == ["M"]
            assert response["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_assist_routes_to_axis_only(self, db_session, mock_trace_id):
        """Test assist signals route to Axis only"""
        payload = {"message": "help me understand"}
        
        with patch('app.router.call_agent') as mock_call:
            mock_call.return_value = {"status": "success", "agent": "Axis"}
            
            agents, response = await route_to_agents(
                db_session,
                "test_log_id", 
                "assist",
                payload,
                mock_trace_id
            )
            
            assert agents == ["Axis"]
            assert response["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_unknown_routes_to_dlq(self, db_session, mock_trace_id):
        """Test unknown signals route to DLQ"""
        payload = {"message": "unrecognized content"}
        
        with patch('app.router.add_to_dlq') as mock_dlq:
            mock_dlq.return_value = True
            
            agents, response = await route_to_agents(
                db_session,
                "test_log_id",
                "unknown", 
                payload,
                mock_trace_id
            )
            
            assert agents == ["DLQ"]
            assert response["status"] == "routed_to_dlq"
            assert response["dlq_logged"] is True
    
    @pytest.mark.asyncio
    async def test_agent_failure_routes_to_dlq(self, db_session, mock_trace_id):
        """Test that when all agents fail, message goes to DLQ"""
        payload = {"message": "emergency situation"}
        
        with patch('app.router.call_agent') as mock_call:
            mock_call.return_value = None  # Simulate agent failure
            
            with patch('app.router.add_to_dlq') as mock_dlq:
                mock_dlq.return_value = True
                
                agents, response = await route_to_agents(
                    db_session,
                    "test_log_id",
                    "emergency",
                    payload, 
                    mock_trace_id
                )
                
                assert agents == ["DLQ"]
                assert response["status"] == "all_agents_failed"
                assert "failed" in response
                assert response["dlq_logged"] is True
    
    @pytest.mark.asyncio
    async def test_partial_agent_success(self, db_session, mock_trace_id):
        """Test routing when some agents succeed and others fail"""
        payload = {"message": "emergency situation"}
        
        async def mock_call_agent(agent, payload, trace_id):
            if agent == "M":
                return {"status": "success", "agent": "M"}
            else:  # Axis fails
                return None
        
        with patch('app.router.call_agent', side_effect=mock_call_agent):
            agents, response = await route_to_agents(
                db_session,
                "test_log_id", 
                "emergency",
                payload,
                mock_trace_id
            )
            
            assert "M" in agents
            assert response["status"] == "success"
            assert "M" in response["successful"]
            assert "Axis" in response["failed"]
    
    @pytest.mark.asyncio
    async def test_trace_id_added_to_payload(self, db_session, mock_trace_id):
        """Test that trace_id is added to agent payload"""
        payload = {"message": "test"}
        
        with patch('app.router.call_agent') as mock_call:
            mock_call.return_value = {"status": "success"}
            
            await route_to_agents(
                db_session,
                "test_log_id",
                "assist", 
                payload,
                mock_trace_id
            )
            
            # Verify call_agent was called with enriched payload
            mock_call.assert_called()
            called_payload = mock_call.call_args[0][1]  # Second argument
            assert called_payload["trace_id"] == mock_trace_id
    
    @pytest.mark.asyncio
    async def test_metrics_recorded(self, db_session, mock_trace_id):
        """Test that metrics are recorded during routing"""
        payload = {"message": "test", "sender_id": "test_user"}
        
        with patch('app.router.SIGNALS_RECEIVED') as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            
            with patch('app.router.call_agent') as mock_call:
                mock_call.return_value = {"status": "success"}
                
                await route_to_agents(
                    db_session,
                    "test_log_id",
                    "assist",
                    payload, 
                    mock_trace_id
                )
                
                # Verify metrics were recorded
                mock_metric.labels.assert_called_with(kind="assist", sender_id="test_user")
                mock_metric.labels.return_value.inc.assert_called()

class TestCallAgent:
    """Test individual agent calling logic"""
    
    @pytest.mark.asyncio
    async def test_dlq_agent_special_case(self, mock_trace_id):
        """Test DLQ agent returns immediately without HTTP call"""
        result = await call_agent("DLQ", {"message": "test"}, mock_trace_id)
        assert result == {"status": "queued_for_dlq"}
    
    @pytest.mark.asyncio 
    async def test_missing_endpoint_raises_error(self, mock_trace_id):
        """Test that missing agent endpoint raises error"""
        with patch('app.router.AGENT_ENDPOINTS', {"M": "http://test"}):
            with pytest.raises(Exception, match="No endpoint configured"):
                await call_agent("NonExistentAgent", {"message": "test"}, mock_trace_id)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_call(self, mock_trace_id):
        """Test that open circuit breaker prevents agent calls"""
        with patch('app.router.circuit_breaker') as mock_cb:
            mock_cb.is_circuit_open.return_value = True
            
            with pytest.raises(Exception, match="Circuit open"):
                await call_agent("TestAgent", {"message": "test"}, mock_trace_id)
    
    @pytest.mark.asyncio
    async def test_successful_agent_response(self, mock_trace_id):
        """Test successful agent response handling"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "result": "processed"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            with patch('app.router.AGENT_ENDPOINTS', {"TestAgent": "http://test.example"}):
                with patch('app.router.circuit_breaker') as mock_cb:
                    mock_cb.is_circuit_open.return_value = False
                    
                    result = await call_agent("TestAgent", {"message": "test"}, mock_trace_id)
                    
                    assert result == {"status": "success", "result": "processed"}
                    mock_cb.record_success.assert_called_with("TestAgent")
    
    @pytest.mark.asyncio
    async def test_agent_error_response(self, mock_trace_id):
        """Test handling of agent error responses"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            with patch('app.router.AGENT_ENDPOINTS', {"TestAgent": "http://test.example"}):
                with patch('app.router.circuit_breaker') as mock_cb:
                    mock_cb.is_circuit_open.return_value = False
                    
                    with pytest.raises(Exception, match="returned status 500"):
                        await call_agent("TestAgent", {"message": "test"}, mock_trace_id)
                    
                    mock_cb.record_failure.assert_called_with("TestAgent")

class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_new_trace_id_format(self):
        """Test trace ID generation"""
        trace_id = new_trace_id()
        
        assert trace_id is not None
        assert len(trace_id) == 32  # UUID4 hex without dashes
        assert all(c in '0123456789abcdef' for c in trace_id)
    
    def test_new_trace_id_uniqueness(self):
        """Test that generated trace IDs are unique"""
        trace_ids = [new_trace_id() for _ in range(100)]
        assert len(set(trace_ids)) == 100  # All should be unique
