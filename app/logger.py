import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the log record.
    """
    def __init__(self, fmt_dict: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.fmt_dict = fmt_dict if fmt_dict is not None else {
            'level': '%(levelname)s',
            'name': '%(name)s',
            'message': '%(message)s',
        }
        self.default_msec_format = '%s.%03d'

    def format(self, record) -> str:
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        record_dict = self._get_record_dict(record)
        record_dict['timestamp'] = self.formatTime(record, self.datefmt)
        return json.dumps(record_dict)

    def _get_record_dict(self, record) -> Dict[str, Any]:
        record_dict = {}
        for key, value in self.fmt_dict.items():
            try:
                record_dict[key] = value % record.__dict__
            except (KeyError, TypeError):
                record_dict[key] = value
            
        # Add the exception info if it exists
        if record.exc_info:
            record_dict['exc_info'] = self.formatException(record.exc_info)
            
        # Add extra fields set with the extra parameter
        if hasattr(record, 'trace_id'):
            record_dict['trace_id'] = record.trace_id
            
        if hasattr(record, 'kind'):
            record_dict['kind'] = record.kind
            
        if hasattr(record, 'sender_id'):
            record_dict['sender_id'] = record.sender_id
            
        # Add any extra attributes in record.__dict__
        for key, value in record.__dict__.items():
            if key not in record_dict and key not in ('args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                          'funcName', 'id', 'levelname', 'levelno', 'lineno',
                          'module', 'msecs', 'message', 'msg', 'name', 'pathname',
                          'process', 'processName', 'relativeCreated', 'stack_info',
                          'thread', 'threadName'):
                record_dict[key] = value
                
        return record_dict

def setup_logger(name='router', level=logging.INFO):
    """
    Set up and return a logger with JSON formatting
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    return logger

# Create the default logger
logger = setup_logger()
