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

def init_telemetry(log_file: str = "telemetry.log"):
    """Initializes global OpenTelemetry tracing configuration."""
    global _initialized
    if _initialized:
        return
        
    provider = TracerProvider()
    
    # Add file exporter
    log_path = os.path.abspath(log_file)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    provider.add_span_processor(SimpleSpanProcessor(CompactFileSpanExporter(log_path)))
    
    # Check for OTLP environment endpoint fallback
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            # Try HTTP OTLP exporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
        except ImportError:
            try:
                # Try gRPC OTLP exporter
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
            except ImportError:
                logger.warning("OpenTelemetry OTLP Exporter package not installed. Skipping OTLP configuration.")
                
    trace.set_tracer_provider(provider)
    _initialized = True

def get_tracer():
    """Returns the package-level tracer instance."""
    return trace.get_tracer("clinical_cohort_mapper")
