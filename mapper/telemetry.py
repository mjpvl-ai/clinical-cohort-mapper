import os
import json
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, BatchSpanProcessor

logger = logging.getLogger(__name__)

class CompactFileSpanExporter(SpanExporter):
    """A custom OpenTelemetry span exporter that writes clean, single-line telemetry logs to a file."""
    def __init__(self, file_path: str):
        self.file_path = file_path

    def export(self, spans):
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                for span in spans:
                    # Convert times from nanoseconds to milliseconds
                    duration_ms = (span.end_time - span.start_time) / 1e6
                    span_data = {
                        "name": span.name,
                        "trace_id": format(span.context.trace_id, "032x"),
                        "span_id": format(span.context.span_id, "016x"),
                        "parent_id": format(span.parent.span_id, "016x") if span.parent else None,
                        "start_time_unix_ms": round(span.start_time / 1e6),
                        "duration_ms": round(duration_ms, 2),
                        "attributes": dict(span.attributes)
                    }
                    f.write(json.dumps(span_data) + "\n")
            return 0
        except Exception as e:
            logger.error(f"Failed to export spans to file: {e}")
            return 1

    def shutdown(self):
        pass


_initialized = False

def _try_otlp(provider, endpoint):
    """Attempt to add an OTLP HTTP exporter to the provider."""
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        # Ensure endpoint has /v1/traces path for Tempo compatibility
        traces_endpoint = endpoint.rstrip("/")
        if not traces_endpoint.endswith("/v1/traces"):
            traces_endpoint += "/v1/traces"

        exporter = OTLPSpanExporter(endpoint=traces_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(f"OTLP exporter configured → {traces_endpoint}")
        return True
    except ImportError:
        return False


def init_telemetry(log_file: str = "telemetry.log"):
    """Initializes global OpenTelemetry tracing configuration."""
    global _initialized
    if _initialized:
        return

    from opentelemetry.sdk.resources import Resource
    resource = Resource.create({"service.name": "clinical-cohort-mapper"})
    provider = TracerProvider(resource=resource)

    # Always add file exporter
    log_path = os.path.abspath(log_file)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    provider.add_span_processor(SimpleSpanProcessor(CompactFileSpanExporter(log_path)))

    # Try OTLP: env var first, then auto-detect Tempo on localhost
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        _try_otlp(provider, otlp_endpoint)
    else:
        # Auto-detect: probe Tempo default OTLP HTTP port
        import socket
        try:
            sock = socket.create_connection(("127.0.0.1", 4318), timeout=0.3)
            sock.close()
            _try_otlp(provider, "http://localhost:4318")
        except (OSError, ConnectionRefusedError):
            pass  # Tempo not running, file-only mode

    trace.set_tracer_provider(provider)
    _initialized = True

def get_tracer():
    """Returns the package-level tracer instance."""
    return trace.get_tracer("clinical_cohort_mapper")

def shutdown_telemetry():
    """Flushes and shuts down the OpenTelemetry provider to ensure all spans are exported."""
    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.info("Telemetry provider shut down successfully.")
    except Exception as e:
        logger.error(f"Error shutting down telemetry provider: {e}")
