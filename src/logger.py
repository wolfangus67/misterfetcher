"""
Centralized logging configuration for Streams Prefetcher
Inspired by stremthru's logging approach with enhanced features:
- Dual format support (text/json)
- Health check filtering
- Contextual logging support
"""

import logging
import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional


class HealthCheckFilter(logging.Filter):
    """Filter to suppress health check logs unless they're errors"""

    def filter(self, record):
        # Check if this is a health check related log
        message = record.getMessage().lower()
        path = getattr(record, 'path', '').lower()

        is_health_check = (
            '/api/health' in message or
            '/api/health' in path or
            'health_check' in message or
            'healthcheck' in message
        )

        if is_health_check:
            # Only allow ERROR and CRITICAL health check logs (for debugging)
            # But downgrade them to DEBUG level
            if record.levelno >= logging.ERROR:
                record.levelno = logging.DEBUG
                record.levelname = 'DEBUG'
                return True
            # Suppress all other health check logs (INFO, DEBUG, WARNING)
            return False

        return True


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output (text format)"""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record):
        # Add color to level name
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname:8}{self.COLORS['RESET']}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record):
        # Build base log entry
        log_entry = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        # Add any extra context fields from the record
        # These are added via logger.info(..., extra={'key': 'value'})
        reserved_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName', 'levelname',
            'levelno', 'lineno', 'module', 'msecs', 'message', 'pathname', 'process',
            'processName', 'relativeCreated', 'thread', 'threadName', 'exc_info',
            'exc_text', 'stack_info', 'asctime', 'getMessage'
        }

        for key, value in record.__dict__.items():
            if key not in reserved_attrs and not key.startswith('_'):
                log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging():
    """Configure logging for the application"""

    # Get log level from environment (default to INFO)
    log_level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Get log format from environment (default to text)
    log_format = os.getenv('LOG_FORMAT', 'text').lower()

    # Create logger
    logger = logging.getLogger('streams_prefetcher')
    logger.setLevel(log_level)
    logger.handlers = []  # Clear any existing handlers

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Add health check filter to suppress health check logs
    console_handler.addFilter(HealthCheckFilter())

    # Choose formatter based on LOG_FORMAT
    if log_format == 'json':
        # JSON format for structured logging (centralized logging systems)
        formatter = JSONFormatter()
    else:
        # Text format with colors (default, human-readable)
        formatter = ColoredFormatter(
            fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = 'streams_prefetcher'):
    """Get a logger instance with consistent configuration"""
    return logging.getLogger(name)


# Initialize default logger
default_logger = setup_logging()
