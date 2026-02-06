"""
Enhanced Logging System with Structured JSON, Correlation IDs, and Detailed Error Context
"""

import logging
import sys
import json
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
import inspect


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging
    Includes correlation IDs, context, and detailed error information
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string
        """
        # Base log structure
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "thread_name": record.threadName,
        }
        
        # Add correlation ID if available
        if hasattr(record, 'correlation_id'):
            log_data["correlation_id"] = record.correlation_id
        
        # Add custom context if available
        if hasattr(record, 'context'):
            log_data["context"] = record.context
        
        # Add request information if available
        if hasattr(record, 'request_info'):
            log_data["request"] = record.request_info
        
        # Add performance metrics if available
        if hasattr(record, 'performance'):
            log_data["performance"] = record.performance
        
        # Add exception information with full stack trace
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
                "stack_trace_lines": traceback.format_exception(*record.exc_info)
            }
        
        # Add custom error details if available
        if hasattr(record, 'error_details'):
            log_data["error_details"] = record.error_details
        
        return json.dumps(log_data, default=str)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable formatter for console output with color coding
    """
    
    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console"""
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Base format
        formatted = f"{color}[{record.levelname}]{reset} "
        formatted += f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        
        # Add correlation ID if available
        if hasattr(record, 'correlation_id'):
            formatted += f"[{record.correlation_id[:8]}] "
        
        formatted += f"{record.name} - {record.getMessage()}"
        
        # Add exception if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


class EnhancedLogger:
    """
    Enhanced logger with structured logging and detailed error tracking
    """
    
    def __init__(
        self,
        name: str,
        log_dir: str = "./logs",
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        max_bytes: int = 50 * 1024 * 1024,  # 50MB
        backup_count: int = 10
    ):
        """
        Initialize enhanced logger
        
        Args:
            name: Logger name
            log_dir: Directory for log files
            console_level: Console logging level
            file_level: File logging level
            max_bytes: Max size per log file
            backup_count: Number of backup files to keep
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)  # Capture all levels
        
        # Avoid duplicate handlers
        if self.logger.handlers:
            return
        
        # Create log directory
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Console Handler (Human-readable with colors)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(ConsoleFormatter())
        self.logger.addHandler(console_handler)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Structured JSON File Handler (For analysis/debugging)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        json_handler = RotatingFileHandler(
            log_path / "rag_api_structured.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        json_handler.setLevel(file_level)
        json_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(json_handler)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Error File Handler (Errors and above only)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        error_handler = RotatingFileHandler(
            log_path / "rag_api_errors.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(error_handler)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Daily Rotating Handler (For audit trail)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        daily_handler = TimedRotatingFileHandler(
            log_path / "rag_api_daily.log",
            when="midnight",
            interval=1,
            backupCount=30  # Keep 30 days
        )
        daily_handler.setLevel(logging.INFO)
        daily_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(daily_handler)
    
    def _add_context(
        self,
        extra: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add context information to log record
        
        Args:
            extra: Existing extra dict
            correlation_id: Request correlation ID
            context: Additional context
            
        Returns:
            Enhanced extra dict
        """
        if extra is None:
            extra = {}
        
        if correlation_id:
            extra['correlation_id'] = correlation_id
        
        if context:
            extra['context'] = context
        
        return extra
    
    def debug(
        self,
        msg: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log debug message with context"""
        extra = self._add_context(kwargs.get('extra'), correlation_id, context)
        self.logger.debug(msg, extra=extra, **{k: v for k, v in kwargs.items() if k != 'extra'})
    
    def info(
        self,
        msg: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log info message with context"""
        extra = self._add_context(kwargs.get('extra'), correlation_id, context)
        self.logger.info(msg, extra=extra, **{k: v for k, v in kwargs.items() if k != 'extra'})
    
    def warning(
        self,
        msg: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log warning message with context"""
        extra = self._add_context(kwargs.get('extra'), correlation_id, context)
        self.logger.warning(msg, extra=extra, **{k: v for k, v in kwargs.items() if k != 'extra'})
    
    def error(
        self,
        msg: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
        **kwargs
    ):
        """Log error message with full context and stack trace"""
        extra = self._add_context(kwargs.get('extra'), correlation_id, context)
        self.logger.error(msg, extra=extra, exc_info=exc_info, **{k: v for k, v in kwargs.items() if k != 'extra'})
    
    def critical(
        self,
        msg: str,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
        **kwargs
    ):
        """Log critical message with full context and stack trace"""
        extra = self._add_context(kwargs.get('extra'), correlation_id, context)
        self.logger.critical(msg, extra=extra, exc_info=exc_info, **{k: v for k, v in kwargs.items() if k != 'extra'})
    
    def log_error_with_context(
        self,
        error: Exception,
        correlation_id: str,
        context: Dict[str, Any],
        severity: str = "ERROR"
    ) -> Dict[str, Any]:
        """
        Log error with comprehensive context including stack traces and variables
        
        Args:
            error: Exception that occurred
            context: Dictionary with relevant context
            correlation_id: Request tracking ID
            severity: Log level (ERROR, CRITICAL, WARNING)
            
        Returns:
            Error details dictionary
        """
        # Get the calling frame info
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_frame = frame.f_back
            caller_info = {
                "filename": caller_frame.f_code.co_filename,
                "function": caller_frame.f_code.co_name,
                "line_number": caller_frame.f_lineno,
                "local_variables": {
                    k: str(v)[:200]  # Limit variable length
                    for k, v in caller_frame.f_locals.items()
                    if not k.startswith('_') and k not in ['self', 'cls']
                }
            }
        else:
            caller_info = {}
        
        # Build comprehensive error details
        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_module": error.__class__.__module__,
            "error_class": error.__class__.__qualname__,
            "stack_trace": traceback.format_exc(),
            "stack_trace_list": traceback.format_tb(error.__traceback__) if error.__traceback__ else [],
            "caller_info": caller_info,
            "context": context,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Create extra dict for structured logging
        extra = {
            'correlation_id': correlation_id,
            'error_details': error_details,
            'context': context
        }
        
        # Log based on severity
        error_msg = f"{severity} [{correlation_id}]: {type(error).__name__}: {str(error)}"
        
        if severity == "CRITICAL":
            self.logger.critical(error_msg, extra=extra, exc_info=True)
        elif severity == "WARNING":
            self.logger.warning(error_msg, extra=extra, exc_info=True)
        else:
            self.logger.error(error_msg, extra=extra, exc_info=True)
        
        return error_details
    
    def log_request(
        self,
        correlation_id: str,
        method: str,
        path: str,
        query_params: Optional[Dict] = None,
        body_params: Optional[Dict] = None,
        client_info: Optional[Dict] = None
    ):
        """
        Log incoming request with full details
        
        Args:
            correlation_id: Request correlation ID
            method: HTTP method
            path: Request path
            query_params: Query parameters
            body_params: Body parameters (sanitized)
            client_info: Client information
        """
        request_info = {
            "method": method,
            "path": path,
            "query_params": query_params or {},
            "body_params": body_params or {},
            "client": client_info or {}
        }
        
        extra = {
            'correlation_id': correlation_id,
            'request_info': request_info
        }
        
        self.logger.info(
            f"[REQUEST-{correlation_id[:8]}] {method} {path}",
            extra=extra
        )
    
    def log_response(
        self,
        correlation_id: str,
        status_code: int,
        duration_seconds: float,
        response_size_bytes: Optional[int] = None
    ):
        """
        Log response with performance metrics
        
        Args:
            correlation_id: Request correlation ID
            status_code: HTTP status code
            duration_seconds: Request duration
            response_size_bytes: Response size
        """
        performance = {
            "duration_seconds": round(duration_seconds, 4),
            "status_code": status_code,
            "response_size_bytes": response_size_bytes
        }
        
        extra = {
            'correlation_id': correlation_id,
            'performance': performance
        }
        
        level_map = {
            range(200, 300): logging.INFO,
            range(300, 400): logging.INFO,
            range(400, 500): logging.WARNING,
            range(500, 600): logging.ERROR
        }
        
        log_level = logging.INFO
        for status_range, level in level_map.items():
            if status_code in status_range:
                log_level = level
                break
        
        self.logger.log(
            log_level,
            f"[RESPONSE-{correlation_id[:8]}] Status: {status_code}, Duration: {duration_seconds:.4f}s",
            extra=extra
        )
    
    def log_step(
        self,
        correlation_id: str,
        step_name: str,
        step_number: int,
        total_steps: int,
        status: str,
        duration: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ):
        """
        Log individual pipeline step with details
        
        Args:
            correlation_id: Request correlation ID
            step_name: Name of the step
            step_number: Step number
            total_steps: Total steps in pipeline
            status: success, failed, skipped
            duration: Step duration in seconds
            result: Step result data
            error: Error if step failed
        """
        context = {
            "step_name": step_name,
            "step_number": step_number,
            "total_steps": total_steps,
            "status": status,
            "duration_seconds": round(duration, 4) if duration else None,
            "result": result
        }
        
        extra = {
            'correlation_id': correlation_id,
            'context': context
        }
        
        icon = {"success": "✓", "failed": "✗", "skipped": "⊘"}.get(status, "•")
        
        msg = f"[{correlation_id[:8]}] STEP {step_number}/{total_steps}: {step_name} - {icon} {status.upper()}"
        
        if duration:
            msg += f" (took {duration:.4f}s)"
        
        if status == "failed" and error:
            self.logger.error(msg, extra=extra, exc_info=(type(error), error, error.__traceback__))
        elif status == "success":
            self.logger.info(msg, extra=extra)
        else:
            self.logger.debug(msg, extra=extra)


def setup_enhanced_logger(name: str) -> EnhancedLogger:
    """
    Factory function to create enhanced logger
    
    Args:
        name: Logger name
        
    Returns:
        EnhancedLogger instance
    """
    return EnhancedLogger(name)