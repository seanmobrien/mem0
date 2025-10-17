"""Shared telemetry helpers for OpenTelemetry tracing."""

from __future__ import annotations

import logging
import inspect
from typing import Optional, Callable
from functools import wraps

from opentelemetry import trace, context as otel_context
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.propagate import extract

_logger = logging.getLogger(__name__)


def _attach_trace_context_from_request(request) -> Optional[object]:
    """Attach OpenTelemetry context derived from incoming request headers."""
    try:
        context = extract(request.headers)
    except Exception as exc:  # pragma: no cover - defensive logging
        _logger.debug("Failed to extract trace context: %s", exc)
        return None
    return otel_context.attach(context)


def _detach_trace_context(token: Optional[object]) -> None:
    """Detach OpenTelemetry context."""
    if token is not None:
        otel_context.detach(token)


def _record_exception(span, exc: Exception) -> None:
    """Record an exception in the current span and set error status."""
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def traced_endpoint(tracer_name: str, span_name: Optional[str] = None, kind: SpanKind = SpanKind.SERVER):
    """
    Decorator for tracing FastAPI endpoints with OpenTelemetry.
    
    Args:
        tracer_name: Name of the tracer (e.g., "mem0.api.apps")
        span_name: Optional custom span name. If not provided, uses function name.
        kind: The kind of span (default: SpanKind.SERVER)
    
    Example:
        from app.utils.telemetry import traced_endpoint, _record_exception
        from opentelemetry import trace
        
        router = APIRouter(prefix="/api/v1/apps", tags=["apps"])
        _TRACER = trace.get_tracer("mem0.api.apps")
        
        @router.get("/")
        @traced_endpoint("mem0.api.apps")
        async def list_items():
            return {"items": []}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(tracer_name)
            name = span_name or f"{func.__module__}.{func.__name__}"
            
            # Extract request from kwargs if available
            request = kwargs.get('request')
            trace_token = None
            if request:
                trace_token = _attach_trace_context_from_request(request)
            
            try:
                with tracer.start_as_current_span(name, kind=kind) as span:
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as exc:
                        _record_exception(span, exc)
                        raise
            finally:
                if trace_token:
                    _detach_trace_context(trace_token)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(tracer_name)
            name = span_name or f"{func.__module__}.{func.__name__}"
            
            # Extract request from kwargs if available
            request = kwargs.get('request')
            trace_token = None
            if request:
                trace_token = _attach_trace_context_from_request(request)
            
            try:
                with tracer.start_as_current_span(name, kind=kind) as span:
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception as exc:
                        _record_exception(span, exc)
                        raise
            finally:
                if trace_token:
                    _detach_trace_context(trace_token)
        
        # Return the appropriate wrapper based on whether the function is async
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
