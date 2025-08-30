import os
import logging
import json
import time
import sys
from datetime import datetime
import structlog
from typing import Dict, Any, Optional

# Configure structlog for structured JSON logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

def get_logger(name: str = "router"):
    """Get a configured structured logger"""
    return structlog.get_logger(name)

class TraceMiddleware:
    """Middleware to add trace_id to all logs for a request"""
    
    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware")
        
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
            
        # Generate or extract trace_id
        trace_id = None
        for key, value in scope.get("headers", []):
            if key.decode("latin1").lower() == "x-trace-id":
                trace_id = value.decode("latin1")
                break
                
        if not trace_id:
            from app.router import new_trace_id
            trace_id = new_trace_id()
            
        # Set trace context for all logs in this request
        ctx = structlog.contextvars.bind_contextvars(trace_id=trace_id)
        
        # Log the request
        path = scope.get("path", "").decode("latin1") if isinstance(scope.get("path", ""), bytes) else scope.get("path", "")
        method = scope.get("method", "").decode("latin1") if isinstance(scope.get("method", ""), bytes) else scope.get("method", "")
        
        self.logger.info(
            "request_start", 
            path=path, 
            method=method,
            trace_id=trace_id,
        )
        
        start_time = time.time()
        
        # Process the request with the trace context
        try:
            await self.app(scope, receive, send)
        except Exception as e:
            self.logger.error(
                "request_error",
                path=path,
                method=method,
                trace_id=trace_id,
                error=str(e),
                duration=time.time() - start_time,
            )
            raise
        finally:
            # Log request completion
            self.logger.info(
                "request_end",
                path=path,
                method=method,
                trace_id=trace_id,
                duration=time.time() - start_time,
            )
            
            # Clean up context vars
            structlog.contextvars.clear_contextvars()

# Helper function to log with trace ID
def log_with_trace(message: str, trace_id: str, level: str = "info", **kwargs):
    """Log a message with trace ID and additional context"""
    logger = get_logger()
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Add trace_id to context
    with structlog.contextvars.bound_contextvars(trace_id=trace_id):
        log_func(message, **kwargs)

# Initialize logging
def init_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(message)s",
        stream=sys.stdout,
    )
