"""
OpenTelemetry tracing setup.

Measures:
  - API endpoint latency  (via FastAPI instrumentation)
  - LLM call latency      (manual spans around each LLM call)

Usage — wrap any LLM call:
    from telemetry.tracing import llm_span

    async with llm_span("intent_classification"):
        result = await intent_agent.run(query)
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

logger = logging.getLogger(__name__)

_tracer: Optional[trace.Tracer] = None


def setup_tracing(service_name: str = "lovdata-rag-api") -> None:
    """
    Initialize OpenTelemetry with a console exporter.

    In production, swap ConsoleSpanExporter for an OTLP exporter
    pointing at your observability backend (Jaeger, Grafana Tempo, etc.).
    """
    global _tracer

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(service_name)
    logger.info(f"[OK] OpenTelemetry tracing initialized | service={service_name}")


def get_tracer() -> trace.Tracer:
    """Return the global tracer (must call setup_tracing first)."""
    if _tracer is None:
        raise RuntimeError("Tracing not initialized. Call setup_tracing() at startup.")
    return _tracer

import time
from opentelemetry.trace import StatusCode


@asynccontextmanager
async def llm_span(operation_name: str):
    """
    Async context manager that wraps an LLM call in a named trace span
    and logs latency in milliseconds.
    """
    tracer = get_tracer()

    start_time = time.perf_counter()

    with tracer.start_as_current_span(f"llm.{operation_name}") as span:
        try:
            yield span

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            raise

        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Attach latency as span attribute
            span.set_attribute("llm.latency_ms", latency_ms)

            # Log clean latency output
            logger.info(
                f"⏱ LLM {operation_name} latency: {latency_ms} ms"
            )
