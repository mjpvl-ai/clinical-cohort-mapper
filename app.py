import time
import httpx
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field

from mapper.schemas import (
    MappingResult, ClinicalIntent, FinalLogic, CandidateCode, SelectedCode, RejectedCandidate
)
from mapper.parser import MedicalLinguist
from mapper.retriever import MedicalInformatician
from mapper.auditor import ClinicalAuditor
from mapper.engine import MappingEngine
from mapper.telemetry import init_telemetry, shutdown_telemetry, get_tracer

# Import OpenTelemetry W3C Trace Context Propagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from a2a.types import AgentCard, AgentSkill, AgentInterface, AgentCapabilities
from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes

# Initialize agents globally
linguist_agent = MedicalLinguist()
informatician_agent = MedicalInformatician()
auditor_agent = ClinicalAuditor()
engine_helper = MappingEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize OpenTelemetry Tracing
    init_telemetry()
    yield
    # Shutdown: Flush and shut down telemetry
    shutdown_telemetry()

app = FastAPI(
    title="Clinical Cohort Mapper - A2A Server",
    description="A multi-agent REST API server utilizing the Agent-to-Agent (A2A) protocol and OpenTelemetry W3C Trace Context propagation.",
    version="1.0.0",
    lifespan=lifespan
)

# Define AgentCard metadata using the official a2a-sdk
agent_card = AgentCard(
    name="clinical-cohort-mapper",
    description="Exposes a consensus-driven multi-agent clinical cohort query mapping engine that transforms natural language patient criteria into standardized terminologies.",
    version="1.0.0",
    documentation_url="https://github.com/jayaprakash/clinical-cohort-mapper",
    supported_interfaces=[
        AgentInterface(
            url="/api/v1/map-cohort",
            protocol_binding="http-rest",
            protocol_version="1.0.0"
        ),
        AgentInterface(
            url="/api/v1/agent/linguist",
            protocol_binding="http-rest",
            protocol_version="1.0.0"
        ),
        AgentInterface(
            url="/api/v1/agent/informatician",
            protocol_binding="http-rest",
            protocol_version="1.0.0"
        ),
        AgentInterface(
            url="/api/v1/agent/auditor",
            protocol_binding="http-rest",
            protocol_version="1.0.0"
        )
    ],
    skills=[
        AgentSkill(
            id="concept-mapping",
            name="Clinical Concept Mapping",
            description="Translates natural language patient criteria to standard clinical codes (LOINC, RxNorm, SNOMED, ICD-10-CM)."
        )
    ],
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False
    )
)

# Register the Agent Card routes using the official A2A SDK
add_a2a_routes_to_fastapi(app, agent_card_routes=create_agent_card_routes(agent_card))

# Request schemas for Agent Endpoints
class LinguistRequest(BaseModel):
    query: str
    critique: Optional[dict] = None

class InformaticianRequest(BaseModel):
    intent: ClinicalIntent

class AuditorRequest(BaseModel):
    intent: ClinicalIntent
    candidates: List[CandidateCode]

class MapCohortRequest(BaseModel):
    query: str
    max_retries: int = Field(default=3, ge=1, le=5)

# --- Agent 1: Medical Linguist ---
@app.post("/api/v1/agent/linguist", response_model=Optional[ClinicalIntent])
async def agent_linguist(req: LinguistRequest, request: Request):
    # Extract W3C trace context from request headers
    headers = dict(request.headers)
    ctx = TraceContextTextMapPropagator().extract(headers)
    
    tracer = get_tracer()
    # Start agent span parented by the orchestrator trace context
    with tracer.start_as_current_span("Linguist.extract_intent", context=ctx) as span:
        intent = linguist_agent.parse(req.query, req.critique)
        if intent:
            span.set_attribute("clinical.domain", intent.domain)
            span.set_attribute("clinical.entities_count", len(intent.clinical_entities))
        return intent

# --- Agent 2: Medical Informatician ---
class InformaticianResponse(BaseModel):
    candidates: List[CandidateCode]
    prog_candidates: List[CandidateCode]

@app.post("/api/v1/agent/informatician", response_model=InformaticianResponse)
async def agent_informatician(req: InformaticianRequest, request: Request):
    # Extract W3C trace context from request headers
    headers = dict(request.headers)
    ctx = TraceContextTextMapPropagator().extract(headers)
    
    tracer = get_tracer()
    with tracer.start_as_current_span("Informatician.retrieve", context=ctx) as span:
        # Programmatic lexical search
        prog_candidates = informatician_agent._retrieve_candidates_programmatic(req.intent)
        # LLM-refined semantic candidate filtering
        candidates = informatician_agent.retrieve_candidates(req.intent)
        
        span.set_attribute("clinical.candidate_count", len(candidates))
        span.set_attribute("clinical.raw_candidate_count", len(prog_candidates))
        
        return InformaticianResponse(
            candidates=candidates,
            prog_candidates=prog_candidates
        )

# --- Agent 3: Clinical Auditor ---
class AuditorResponse(BaseModel):
    is_approved: bool
    selected: List[SelectedCode]
    rejected: List[RejectedCandidate]
    critique: Optional[dict] = None

@app.post("/api/v1/agent/auditor", response_model=AuditorResponse)
async def agent_auditor(req: AuditorRequest, request: Request):
    # Extract W3C trace context from request headers
    headers = dict(request.headers)
    ctx = TraceContextTextMapPropagator().extract(headers)
    
    tracer = get_tracer()
    with tracer.start_as_current_span("Auditor.validate_codes", context=ctx) as span:
        is_approved, selected, rejected, critique = auditor_agent.audit(req.intent, req.candidates)
        span.set_attribute("clinical.is_approved", is_approved)
        span.set_attribute("clinical.selected_count", len(selected))
        span.set_attribute("clinical.rejected_count", len(rejected))
        
        return AuditorResponse(
            is_approved=is_approved,
            selected=selected,
            rejected=rejected,
            critique=critique
        )

# --- Gateway Orchestrator ---
@app.post("/api/v1/map-cohort", response_model=MappingResult)
async def map_cohort(req: MapCohortRequest, request: Request):
    query = req.query
    max_retries = req.max_retries
    
    start_time = time.time()
    trace_id = f"t-{int(start_time)}-{hash(query) & 0xffff}"
    
    # Dynamically resolve server base URL from request details
    base_url = str(request.base_url).rstrip('/')
    
    tracer = get_tracer()
    # Start the orchestrator span (Root span of this query execution)
    with tracer.start_as_current_span("MapClinicalQuery") as span:
        span.set_attribute("clinical.query", query)
        
        attempt = 0
        critique = None
        is_approved = False
        intent = None
        candidates = []
        all_candidates = []
        selected = []
        rejected = []
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            while not is_approved and attempt < max_retries:
                # 1. Ask Linguist Agent for intent extraction
                headers = {}
                TraceContextTextMapPropagator().inject(headers)
                
                linguist_resp = await client.post(
                    f"{base_url}/api/v1/agent/linguist",
                    json={"query": query, "critique": critique},
                    headers=headers
                )
                if not linguist_resp.is_success:
                    raise HTTPException(status_code=502, detail="Failed communicating with Linguist Agent")
                
                intent_data = linguist_resp.json()
                if not intent_data:
                    break
                intent = ClinicalIntent(**intent_data)
                
                # 2. Ask Informatician Agent for candidates retrieval
                headers = {}
                TraceContextTextMapPropagator().inject(headers)
                informatician_resp = await client.post(
                    f"{base_url}/api/v1/agent/informatician",
                    json={"intent": intent.model_dump()},
                    headers=headers
                )
                if not informatician_resp.is_success:
                    raise HTTPException(status_code=502, detail="Failed communicating with Informatician Agent")
                
                inf_data = informatician_resp.json()
                candidates = [CandidateCode(**c) for c in inf_data["candidates"]]
                prog_candidates = [CandidateCode(**c) for c in inf_data["prog_candidates"]]
                
                # Track filtered-out candidates (rejected due to LLM refinement)
                filtered_out = [
                    c for c in prog_candidates 
                    if c.code not in [fc.code for fc in candidates]
                ]
                for rc in filtered_out:
                    if rc.code not in [rj.code for rj in rejected]:
                        rejected.append(RejectedCandidate(
                            vocabulary=rc.vocabulary,
                            code=rc.code,
                            display=rc.display,
                            reason="Filtered out during search refinement (too general or unrelated)."
                        ))
                
                # Compile candidate master list
                for c in candidates:
                    if c.code not in [ac.code for ac in all_candidates]:
                        all_candidates.append(c)
                for c in prog_candidates:
                    if c.code not in [ac.code for ac in all_candidates]:
                        all_candidates.append(c)
                
                # 3. Ask Auditor Agent for validation & consensus
                headers = {}
                TraceContextTextMapPropagator().inject(headers)
                auditor_resp = await client.post(
                    f"{base_url}/api/v1/agent/auditor",
                    json={
                        "intent": intent.model_dump(),
                        "candidates": [c.model_dump() for c in candidates]
                    },
                    headers=headers
                )
                if not auditor_resp.is_success:
                    raise HTTPException(status_code=502, detail="Failed communicating with Clinical Auditor Agent")
                
                aud_data = auditor_resp.json()
                is_approved = aud_data["is_approved"]
                critique = aud_data["critique"]
                selected = [SelectedCode(**sc) for sc in aud_data["selected"]]
                
                # Merge Auditor rejections
                for r in aud_data["rejected"]:
                    rc = RejectedCandidate(**r)
                    if rc.code not in [rj.code for rj in rejected]:
                        rejected.append(rc)
                
                attempt += 1
            
            # Fallback Audit if nothing was selected but candidates were retrieved
            if not selected and all_candidates:
                fallback_intent = linguist_agent.parse(query, None)
                headers = {}
                TraceContextTextMapPropagator().inject(headers)
                auditor_resp = await client.post(
                    f"{base_url}/api/v1/agent/auditor",
                    json={
                        "intent": fallback_intent.model_dump(),
                        "candidates": [c.model_dump() for c in all_candidates]
                    },
                    headers=headers
                )
                if auditor_resp.is_success:
                    aud_data = auditor_resp.json()
                    selected = [SelectedCode(**sc) for sc in aud_data["selected"]]
            
            # Finalize ranking & mapping logic via MappingEngine helpers
            all_candidates = engine_helper._rank_candidates(intent, all_candidates, selected)
            final_logic = engine_helper._generate_final_logic(intent)
            
            # Trace Span Details
            if intent:
                span.set_attribute("clinical.domain", intent.domain)
            span.set_attribute("clinical.concept_count", len(all_candidates))
            span.set_attribute("clinical.attempts", attempt)
            if selected:
                span.set_attribute("clinical.top_code", f"{selected[0].vocabulary}:{selected[0].code}")
                span.set_attribute("clinical.status", "success")
            else:
                span.set_attribute("clinical.status", "unverified")
            
            metadata = {
                'trace_id': trace_id,
                'duration_ms': round((time.time() - start_time) * 1000, 2),
                'correction_attempts': attempt - 1,
                'status': 'success' if selected else 'unverified',
                'a2a_orchestration': True
            }
            
            return MappingResult(
                query=query,
                interpreted_meaning=intent,
                candidate_codes=all_candidates,
                selected_codes=selected,
                rejected_candidates=rejected,
                final_logic=final_logic,
                metadata=metadata
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
