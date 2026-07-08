from typing import Literal

from pydantic import BaseModel, Field


class Constraint(BaseModel):
    operator: str  # '>', '<', '>=', '<=', '==', 'in'
    value: float | int | str | list[int | str]
    unit: str | None = None


class ClinicalIntent(BaseModel):
    original_query: str
    clinical_entities: list[str]
    synonyms: list[str] = Field(default_factory=list)
    domain: Literal["measurement", "condition", "drug", "procedure", "observation"]
    constraint: Constraint | None = None
    status: Literal["current", "prior", "any"] = "any"
    negative_constraints: list[str] = Field(default_factory=list)


class CandidateCode(BaseModel):
    vocabulary: str
    code: str
    display: str
    rank: int


class SelectedCode(BaseModel):
    vocabulary: str
    code: str
    display: str
    confidence: float
    reason: str


class RejectedCandidate(BaseModel):
    vocabulary: str
    code: str
    display: str
    reason: str


class FinalLogic(BaseModel):
    concept: str
    condition: str


class MappingResult(BaseModel):
    query: str
    interpreted_meaning: ClinicalIntent
    candidate_codes: list[CandidateCode] = Field(default_factory=list)
    selected_codes: list[SelectedCode] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    final_logic: FinalLogic
    metadata: dict | None = Field(default_factory=dict)
