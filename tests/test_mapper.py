import pytest
import os
import sys

# Ensure mapper is importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper.engine import MappingEngine
from mapper.schemas import MappingResult

# Set up OpenTelemetry InMemorySpanExporter for testing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

provider = TracerProvider()
memory_exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
trace.set_tracer_provider(provider)

@pytest.fixture
def engine():
    return MappingEngine()

def test_hba1c_mapping(engine):
    query = "Patients with HbA1c above 7%"
    result = engine.map_query(query)
    
    assert isinstance(result, MappingResult)
    assert result.interpreted_meaning.domain == "measurement"
    assert result.interpreted_meaning.constraint.operator == ">"
    assert result.interpreted_meaning.constraint.value == 7
    assert result.interpreted_meaning.constraint.unit == "%"
    
    # Check that we selected LOINC code 4548-4
    selected_codes = [c.code for c in result.selected_codes]
    assert "4548-4" in selected_codes

def test_metformin_mapping(engine):
    query = "Patients currently taking metformin"
    result = engine.map_query(query)
    
    assert result.interpreted_meaning.domain == "drug"
    assert result.interpreted_meaning.status == "current"
    
    # Metformin RxNorm code is 6809
    selected_codes = [c.code for c in result.selected_codes]
    assert "6809" in selected_codes

def test_diabetes_mapping(engine):
    query = "Patients diagnosed with type 2 diabetes"
    result = engine.map_query(query)
    
    assert result.interpreted_meaning.domain == "condition"
    selected_codes = [c.code for c in result.selected_codes]
    assert any(code.startswith("E11") for code in selected_codes)

def test_ckd_stage_3_self_correction(engine):
    query = "Patients with chronic kidney disease stage 3"
    result = engine.map_query(query)
    
    assert result.interpreted_meaning.domain == "condition"
    
    # Check that unspecified chronic kidney disease (N18.9) is rejected/absent from selected
    selected_codes = [c.code for c in result.selected_codes]
    assert "N18.9" not in selected_codes
    
    # Check that N18.30, N18.31, or N18.32 are present
    assert any(code in selected_codes for code in ["N18.30", "N18.31", "N18.32"])
    
    # N18.9 should be in rejected candidates
    rejected_codes = [c.code for c in result.rejected_candidates]
    assert "N18.9" in rejected_codes

def test_glp1_class_expansion(engine):
    query = "Patients on GLP-1 receptor agonists"
    result = engine.map_query(query)
    
    assert result.interpreted_meaning.domain == "drug"
    
    # Selected codes should contain active ingredients of GLP-1 agonists (e.g. semaglutide, liraglutide, dulaglutide)
    selected_names = [c.display.lower() for c in result.selected_codes]
    assert any(name in selected_names for name in ["semaglutide", "liraglutide", "dulaglutide", "exenatide", "lixisenatide"])

def test_colonoscopy_procedure(engine):
    query = "Patients who had a colonoscopy"
    result = engine.map_query(query)
    
    assert result.interpreted_meaning.domain == "procedure"
    selected_codes = [c.code for c in result.selected_codes]
    assert "73761001" in selected_codes  # SNOMED code for colonoscopy

def test_opentelemetry_tracing(engine):
    # Clear memory exporter spans
    memory_exporter.clear()
    
    query = "Patients with LDL cholesterol below 100 mg/dL"
    result = engine.map_query(query)
    
    # Retrieve exported spans
    spans = memory_exporter.get_finished_spans()
    
    # Check that spans were exported
    assert len(spans) > 0
    
    # Find the root span "MapClinicalQuery"
    root_span = next((s for s in spans if s.name == "MapClinicalQuery"), None)
    assert root_span is not None
    assert root_span.attributes["clinical.query"] == query
    assert root_span.attributes["clinical.domain"] == "measurement"
    assert "clinical.top_code" in root_span.attributes
    assert root_span.attributes["clinical.status"] == "success"
    
    # Find child spans
    parser_span = next((s for s in spans if s.name == "Parser.parse_query"), None)
    assert parser_span is not None
    assert parser_span.parent.span_id == root_span.context.span_id
    assert parser_span.attributes["clinical.attempt"] == 0
    assert parser_span.attributes["clinical.domain"] == "measurement"
    
    retrieve_span = next((s for s in spans if s.name == "TerminologyClient.retrieve"), None)
    assert retrieve_span is not None
    assert retrieve_span.parent.span_id == root_span.context.span_id
    assert "clinical.candidate_count" in retrieve_span.attributes
    
    audit_span = next((s for s in spans if s.name == "Auditor.audit"), None)
    assert audit_span is not None
    assert audit_span.parent.span_id == root_span.context.span_id
    assert audit_span.attributes["clinical.is_approved"] == True

def test_opentelemetry_self_correction_span(engine):
    memory_exporter.clear()
    
    query = "Patients with chronic kidney disease stage 3"
    result = engine.map_query(query)
    
    spans = memory_exporter.get_finished_spans()
    
    # Check if there is a SynonymAgent.expand span (only if correction loop triggered)
    expand_span = next((s for s in spans if s.name == "SynonymAgent.expand"), None)
    root_span = next((s for s in spans if s.name == "MapClinicalQuery"), None)
    assert root_span is not None
    
    attempts = root_span.attributes.get("clinical.attempts", 0)
    if attempts > 1:
        assert expand_span is not None
        assert expand_span.parent.span_id == root_span.context.span_id
        assert expand_span.attributes["clinical.attempt"] >= 1
