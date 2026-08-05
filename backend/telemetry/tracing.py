import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.trace import StatusCode

from config import settings

logger = logging.getLogger(__name__)

_tracer: Optional[trace.Tracer] = None


def setup_tracing(service_name: str = "lovdata-rag-api") -> None:
    """
    Initialize OpenTelemetry with a console exporter and standard Resource metadata.
    """
    global _tracer

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": getattr(settings, "ENVIRONMENT", "development"),
    })

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(service_name)
    logger.info(f"[OK] OpenTelemetry tracing initialized | service={service_name} | env={getattr(settings, 'ENVIRONMENT', 'development')}")


def get_tracer() -> trace.Tracer:
    """Return the global tracer (must call setup_tracing first)."""
    if _tracer is None:
        raise RuntimeError("Tracing not initialized. Call setup_tracing() at startup.")
    return _tracer


@asynccontextmanager
async def llm_span(
    operation_name: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model_name: Optional[str] = "gpt-4o-mini",
):
    
    tracer = get_tracer()

    start_time = time.perf_counter()

    with tracer.start_as_current_span(f"llm.{operation_name}") as span:
        span.set_attribute("llm.operation", operation_name)
        span.set_attribute("ai.provider", "Azure OpenAI")
        if model_name:
            span.set_attribute("ai.model", model_name)
        if conversation_id:
            span.set_attribute("conversation.id", str(conversation_id))
        if user_id:
            span.set_attribute("user.id", str(user_id))

        try:
            yield span

        except GeneratorExit:
            # Client closed WebSocket stream / generator exit — detach span context cleanly
            pass

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            raise

        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            span.set_attribute("llm.latency_ms", latency_ms)
            logger.info(f"⏱ LLM {operation_name} latency: {latency_ms} ms")
