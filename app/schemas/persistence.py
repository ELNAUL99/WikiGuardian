from pydantic import BaseModel, ConfigDict

from app.schemas.verification import (
    ExtractedClaim,
    CritiqueAgentResult,
    DecisionAgentResult,
    ResearchSource,
    VerificationAgentResult,
)


class ClaimExecutionRecord(BaseModel):
    """Complete audit record for one processed factual claim."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    claim: ExtractedClaim
    sources: list[ResearchSource]
    verification_rounds: list[VerificationAgentResult]
    critique_rounds: list[CritiqueAgentResult]
    decision: DecisionAgentResult


class VerificationRunMetadata(BaseModel):
    """Metadata required to persist a verification run."""

    proposal_id: str
    llm_model: str
    embedding_model: str


class VerificationRunSummary(BaseModel):
    """Database identifiers returned after persistence."""

    run_id: int
    claim_id_map: dict[str, int]
    evidence_id_map: dict[str, int]


