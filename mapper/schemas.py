from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal

class Constraint(BaseModel):
    operator: str  # '>', '<', '>=', '<=', '==', 'in'
    value: Union[float, int, str, List[Union[int, str]]]
    unit: Optional[str] = None

class ClinicalIntent(BaseModel):
    original_query: str
    clinical_entities: List[str]
    synonyms: List[str] = Field(default_factory=list)
    domain: Literal["measurement", "condition", "drug", "procedure", "observation"]
    constraint: Optional[Constraint] = None
    status: Literal["current", "prior", "any"] = "any"
    negative_constraints: List[str] = Field(default_factory=list)

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
    candidate_codes: List[CandidateCode] = Field(default_factory=list)
    selected_codes: List[SelectedCode] = Field(default_factory=list)
    rejected_candidates: List[RejectedCandidate] = Field(default_factory=list)
    final_logic: FinalLogic
    metadata: Optional[dict] = Field(default_factory=dict)
