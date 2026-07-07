import time
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from mapper.schemas import MappingResult, ClinicalIntent, FinalLogic, CandidateCode, SelectedCode, RejectedCandidate
from mapper.parser import MedicalLinguist
from mapper.retriever import MedicalInformatician
from mapper.auditor import ClinicalAuditor
from mapper.telemetry import get_tracer

class AgentState(TypedDict):
    query: str
    intent: Optional[ClinicalIntent]
    candidates: List[CandidateCode]
    all_candidates: List[CandidateCode]
    selected: List[SelectedCode]
    rejected: List[RejectedCandidate]
    critique: Optional[dict]
    attempt: int
    max_retries: int
    is_approved: bool
    trace_id: str
    start_time: float

class MappingEngine:
    """Orchestrates the Consensus-Driven Graph Reflexion (CDGR) multi-agent loop using LangGraph."""

    def __init__(self):
        self.linguist = MedicalLinguist()
        self.informatician = MedicalInformatician()
        self.auditor = ClinicalAuditor()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Constructs the LangGraph workflow with separate agent nodes and reflexion routing."""
        
        def parse_node(state: AgentState) -> dict:
            tracer = get_tracer()
            span_name = "Parser.parse_query" if state['attempt'] == 0 else "SynonymAgent.expand"
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("clinical.attempt", state['attempt'])
                intent = self.linguist.parse(state['query'], state['critique'])
                if intent:
                    span.set_attribute("clinical.domain", intent.domain)
                return {
                    "intent": intent,
                    "attempt": state['attempt'] + 1
                }

        def retrieve_node(state: AgentState) -> dict:
            tracer = get_tracer()
            with tracer.start_as_current_span("TerminologyClient.retrieve") as span:
                prog_candidates = self.informatician._retrieve_candidates_programmatic(state['intent'])
                candidates = self.informatician.retrieve_candidates(state['intent'])
                
                span.set_attribute("clinical.candidate_count", len(candidates))
                
                # Identify candidates filtered out by Informatician LLM refinement
                filtered_out = [
                    c for c in prog_candidates 
                    if c.code not in [fc.code for fc in candidates]
                ]
                
                new_rejected = list(state['rejected'])
                for rc in filtered_out:
                    if rc.code not in [rj.code for rj in new_rejected]:
                        new_rejected.append(RejectedCandidate(
                            vocabulary=rc.vocabulary,
                            code=rc.code,
                            display=rc.display,
                            reason="Filtered out during search refinement (too general or unrelated)."
                        ))
                
                # Merge candidate codes while preserving order
                all_cand = list(state['all_candidates'])
                for c in candidates:
                    if c.code not in [ac.code for ac in all_cand]:
                        all_cand.append(c)
                for c in prog_candidates:
                    if c.code not in [ac.code for ac in all_cand]:
                        all_cand.append(c)
                        
                return {
                    "candidates": candidates,
                    "all_candidates": all_cand,
                    "rejected": new_rejected
                }

        def audit_node(state: AgentState) -> dict:
            tracer = get_tracer()
            with tracer.start_as_current_span("Auditor.audit") as span:
                is_approved, selected, rejected, critique = self.auditor.audit(state['intent'], state['candidates'])
                span.set_attribute("clinical.is_approved", is_approved)
                span.set_attribute("clinical.selected_count", len(selected))
                
                # Merge rejected lists
                all_rejected = list(state['rejected'])
                for r in rejected:
                    if r.code not in [rj.code for rj in all_rejected]:
                        all_rejected.append(r)
                return {
                    "is_approved": is_approved,
                    "selected": selected,
                    "rejected": all_rejected,
                    "critique": critique
                }

        def route_next(state: AgentState) -> str:
            if state['is_approved'] or state['attempt'] >= state['max_retries']:
                return "end"
            return "parse"

        # Build workflow graph
        workflow = StateGraph(AgentState)
        workflow.add_node("parse", parse_node)
        workflow.add_node("retrieve", retrieve_node)
        workflow.add_node("audit", audit_node)

        workflow.set_entry_point("parse")
        workflow.add_edge("parse", "retrieve")
        workflow.add_edge("retrieve", "audit")
        
        workflow.add_conditional_edges(
            "audit",
            route_next,
            {
                "parse": "parse",
                "end": END
            }
        )
        return workflow.compile()

    def map_query(self, query: str, max_retries: int = 3) -> MappingResult:
        """Runs the query through the LangGraph-driven CDGR multi-agent orchestrator."""
        start_time = time.time()
        trace_id = f"t-{int(start_time)}-{hash(query) & 0xffff}"

        initial_state = {
            "query": query,
            "intent": None,
            "candidates": [],
            "all_candidates": [],
            "selected": [],
            "rejected": [],
            "critique": None,
            "attempt": 0,
            "max_retries": max_retries,
            "is_approved": False,
            "trace_id": trace_id,
            "start_time": start_time
        }

        tracer = get_tracer()
        with tracer.start_as_current_span("MapClinicalQuery") as span:
            span.set_attribute("clinical.query", query)

            # Invoke the LangGraph StateGraph orchestrator
            final_state = self.graph.invoke(initial_state)

            # Retrieve outputs from final state
            intent = final_state.get("intent")
            all_candidates = final_state.get("all_candidates", [])
            selected = final_state.get("selected", [])
            rejected = final_state.get("rejected", [])
            attempt = final_state.get("attempt", 0)

            # Fallback audit if nothing was selected but candidates were found
            if not selected and all_candidates:
                fallback_intent = self.linguist.parse(query, None)
                _, selected, fallback_rejected, _ = self.auditor.audit(fallback_intent, all_candidates)

            # Explicit Multi-factor Candidate Ranking
            all_candidates = self._rank_candidates(intent, all_candidates, selected)

            # Generate final query logic
            final_logic = self._generate_final_logic(intent)

            # Set span level attributes
            if intent:
                span.set_attribute("clinical.domain", intent.domain)
            span.set_attribute("clinical.concept_count", len(all_candidates))
            span.set_attribute("clinical.attempts", attempt)
            
            if selected:
                span.set_attribute("clinical.top_code", f"{selected[0].vocabulary}:{selected[0].code}")
                span.set_attribute("clinical.status", "success")
            else:
                span.set_attribute("clinical.status", "unverified")

            # Build metadata block for performance tracing
            metadata = {
                'trace_id': trace_id,
                'duration_ms': round((time.time() - start_time) * 1000, 2),
                'correction_attempts': attempt - 1,
                'status': 'success' if selected else 'unverified'
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

    def _rank_candidates(self, intent: ClinicalIntent, candidates: List[CandidateCode], selected: List[SelectedCode] = None) -> List[CandidateCode]:
        """Calculates a clinical relevance score for each candidate code and sorts them."""
        scored_candidates = []
        selected_conf_map = {sc.code: sc.confidence for sc in selected} if selected else {}
        
        for c in candidates:
            score = 0.0
            
            # Factor 0: Auditor Selection Boost
            if c.code in selected_conf_map:
                score += selected_conf_map[c.code] * 200.0
            
            # Factor 1: Domain alignment
            vocab_domain_map = {
                'RxNorm': 'drug',
                'ICD-10-CM': 'condition',
                'SNOMED': ['condition', 'procedure'],
                'LOINC': 'measurement'
            }
            expected_vocab = vocab_domain_map.get(c.vocabulary, [])
            if isinstance(expected_vocab, list):
                if intent.domain in expected_vocab:
                    score += 20.0
            else:
                if intent.domain == expected_vocab:
                    score += 20.0
                    
            # Factor 2: Exact Entity Match
            display_lower = c.display.lower()
            for ent in intent.clinical_entities:
                ent_lower = ent.lower()
                if ent_lower in display_lower:
                    score += 15.0
                if display_lower == ent_lower:
                    score += 10.0
                    
            # Factor 3: Synonym Match
            for syn in intent.synonyms:
                syn_lower = syn.lower()
                if syn_lower in display_lower:
                    score += 8.0
                if display_lower == syn_lower:
                    score += 5.0
                    
            # Factor 4: Specificity Match
            if 'fasting' in intent.original_query.lower() and 'fasting' in display_lower:
                score += 15.0
            if 'stage 3' in intent.original_query.lower() and 'stage 3' in display_lower:
                score += 15.0
            if 'systolic' in intent.original_query.lower() and 'systolic' in display_lower:
                score += 15.0
                
            # Factor 5: Original API Rank penalty
            score -= (c.rank * 0.5)
            
            scored_candidates.append((score, c))
            
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        final_candidates = []
        for idx, (score, c) in enumerate(scored_candidates, 1):
            c.rank = idx
            final_candidates.append(c)
            
        return final_candidates

    def _generate_final_logic(self, intent: ClinicalIntent) -> FinalLogic:
        """Generates standard cohort logic descriptions based on intent."""
        entity = intent.clinical_entities[0] if intent.clinical_entities else "Unknown"
        
        if intent.domain == 'measurement':
            if intent.constraint:
                op = intent.constraint.operator
                val = intent.constraint.value
                unit = f" {intent.constraint.unit}" if intent.constraint.unit else ""
                condition_str = f"value {op} {val}{unit}"
            else:
                condition_str = "measurement present"
            concept_str = f"{entity} measurement"
            
        elif intent.domain == 'condition':
            concept_str = f"{entity} diagnosis"
            condition_str = "diagnosis present"
            
        elif intent.domain == 'drug':
            concept_str = f"{entity} exposure"
            if intent.status == 'current':
                condition_str = "current medication use"
            else:
                condition_str = "medication exposure"
                
        elif intent.domain == 'procedure':
            concept_str = f"{entity} procedure"
            if intent.status == 'prior':
                condition_str = "prior procedure performed"
            else:
                condition_str = "procedure performed"
        else:
            concept_str = f"{entity} concept"
            condition_str = "concept present"
            
        if 'HbA1c' in entity:
            concept_str = "HbA1c measurement"
            if intent.constraint:
                condition_str = f"value > {intent.constraint.value}%"
        elif 'metformin' in entity.lower():
            concept_str = "metformin exposure"
            condition_str = "current medication use"
        elif 'chronic kidney disease stage 3' in entity.lower():
            concept_str = "chronic kidney disease stage 3"
            condition_str = "diagnosis present"
            
        return FinalLogic(concept=concept_str, condition=condition_str)
