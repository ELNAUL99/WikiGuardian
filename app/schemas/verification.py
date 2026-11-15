from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceType(str, Enum):
    INTERNAL_WIKIPEDIA = "internal_wikipedia"
    EXTERNAL_SOURCE = "external_source"


class AgentStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    verification_status: VerificationStatus = (
        VerificationStatus.INSUFFICIENT_EVIDENCE
    )


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    claim_id: str
    evidence_type: EvidenceType
    source_title: str
    source_url: Optional[HttpUrl] = None
    source_date: Optional[str] = None
    excerpt: str
    relevance_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    supports_claim: Optional[bool] = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    status: AgentStatus
    summary: str
    reasoning: str = ""
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CritiqueObjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objection_id: str
    claim_id: str
    objection: str
    severity: str
    requires_reassessment: bool = True


class ClaimDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verdict: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    critique_objections: list[str] = Field(default_factory=list)
    reasoning: str
    requires_human_review: bool = True


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: str
    proposal_id: str
    decisions: list[ClaimDecision]
    overall_summary: str
    requires_human_review: bool = True
    warnings: list[str] = Field(default_factory=list)

# --------------------------------------------------
# PLANNER CONTRACTS
# --------------------------------------------------

from pydantic import model_validator


class PlannerTaskType(str, Enum):
    EXTRACT_CLAIMS = "extract_claims"
    INTERNAL_RETRIEVAL = "internal_retrieval"
    EXTERNAL_RESEARCH = "external_research"
    HISTORICAL_REVIEW = "historical_review"


class PlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    article_title: str
    language_code: str
    edit_summary: str = ""
    old_text: str = ""
    proposed_text: str


class PlannerTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: PlannerTaskType
    rationale: str
    priority: int = Field(ge=1, le=5)
    required: bool = True


class VerificationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    objective: str
    tasks: list[PlannerTask]
    max_critique_rounds: int = Field(default=2, ge=0, le=2)
    rationale: str

    @model_validator(mode="after")
    def validate_plan(self):
        task_ids = [task.task_id for task in self.tasks]

        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique")

        task_types = {task.task_type for task in self.tasks}

        if PlannerTaskType.EXTRACT_CLAIMS not in task_types:
            raise ValueError(
                "Every verification plan must include claim extraction"
            )

        return self

# --------------------------------------------------
# CLAIM EXTRACTION CONTRACTS
# --------------------------------------------------

class ClaimExtractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    article_title: str
    language_code: str
    old_text: str = ""
    proposed_text: str


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    subject: str
    predicate: str
    object: str
    context: str = ""
    source_text: str


class ClaimExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    claims: list[ExtractedClaim]
    extraction_summary: str

    @model_validator(mode="after")
    def validate_claims(self):
        claim_ids = [claim.claim_id for claim in self.claims]

        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Claim IDs must be unique")

        for claim in self.claims:
            if not claim.claim_text.strip():
                raise ValueError("Claim text cannot be empty")

        return self

# --------------------------------------------------
# KNOWLEDGE RETRIEVAL CONTRACTS
# --------------------------------------------------

import math
from pydantic import field_validator


class KnowledgeRetrievalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    embedding: list[float] = Field(
        min_length=1024,
        max_length=1024
    )
    top_k: int = Field(default=5, ge=1, le=20)
    language_code: Optional[str] = None

    @field_validator("embedding")
    @classmethod
    def validate_embedding_values(cls, values):
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Embedding values must be finite numbers")
        return values


class KnowledgeMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    article_id: int
    title: str
    language_code: str
    article_url: Optional[str] = None
    wikipedia_revision_id: Optional[int] = None
    wikipedia_timestamp: Optional[str] = None
    chunk_index: int
    section_title: Optional[str] = None
    chunk_text: str
    cosine_distance: float


class KnowledgeRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    matches: list[KnowledgeMatch]
    candidates_examined: int
    summary: str

# --------------------------------------------------
# EXTERNAL RESEARCH CONTRACTS
# --------------------------------------------------

class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    claim_id: str
    claim_text: str
    language_code: str = "en"
    search_query: Optional[str] = None
    max_results: int = Field(default=8, ge=1, le=20)
    scrape_top_n: int = Field(default=3, ge=1, le=5)
    location: Optional[str] = None

    @field_validator("claim_text")
    @classmethod
    def validate_claim_text(cls, value):
        if not value.strip():
            raise ValueError("Claim text cannot be empty")
        return value.strip()

    @field_validator("location")
    @classmethod
    def validate_location(cls, value):
        if value is not None:
            value = value.strip().upper()
            if len(value) != 2 or not value.isalpha():
                raise ValueError(
                    "Location must be a two-letter country code"
                )
        return value


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    url: HttpUrl
    evidence_type: EvidenceType = EvidenceType.EXTERNAL_SOURCE

    search_snippet: Optional[str] = None
    content: str
    search_position: Optional[int] = Field(default=None, ge=1)
    source_date: Optional[str] = None
    retrieved_at: str

    # Internal Wikipedia provenance
    article_id: Optional[int] = None
    chunk_id: Optional[int] = None
    language_code: Optional[str] = None
    wikipedia_revision_id: Optional[int] = None
    wikipedia_timestamp: Optional[str] = None
    cosine_distance: Optional[float] = Field(
        default=None, ge=0.0, le=2.0
    )


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    claim_id: str
    search_query: str
    sources: list[ResearchSource]
    candidates_found: int = Field(ge=0)
    pages_scraped: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    summary: str

    @model_validator(mode="after")
    def validate_research_result(self):
        source_ids = [
            source.source_id for source in self.sources
        ]

        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate research source IDs")

        source_urls = [
            str(source.url) for source in self.sources
        ]

        if len(source_urls) != len(set(source_urls)):
            raise ValueError("Duplicate research source URLs")

        if self.pages_scraped != len(self.sources):
            raise ValueError(
                "pages_scraped must equal the number of sources"
            )

        return self

# --------------------------------------------------
# VERIFICATION AGENT CONTRACTS
# --------------------------------------------------

class EvidencePosition(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class VerificationAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    sources: list[ResearchSource]


class SourceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    position: EvidencePosition
    relevance: float = Field(ge=0, le=1)
    reasoning: str
    quoted_excerpt: Optional[str] = None
    limitations: list[str] = Field(default_factory=list)


class VerificationAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verdict: VerificationStatus
    confidence: float = Field(ge=0, le=1)
    source_assessments: list[SourceAssessment]
    supporting_source_ids: list[str]
    contradicting_source_ids: list[str]
    reasoning: str
    caveats: list[str] = Field(default_factory=list)
    requires_human_review: bool = True

    @model_validator(mode="after")
    def validate_source_references(self):
        assessed_ids = {
            item.source_id for item in self.source_assessments
        }

        if len(assessed_ids) != len(self.source_assessments):
            raise ValueError("Duplicate source assessments")

        supporting = self.supporting_source_ids
        contradicting = self.contradicting_source_ids

        if len(supporting) != len(set(supporting)):
            raise ValueError("Duplicate supporting source IDs")

        if len(contradicting) != len(set(contradicting)):
            raise ValueError("Duplicate contradicting source IDs")

        if not set(supporting).issubset(assessed_ids):
            raise ValueError(
                "Supporting source IDs must have assessments"
            )

        if not set(contradicting).issubset(assessed_ids):
            raise ValueError(
                "Contradicting source IDs must have assessments"
            )

        if set(supporting) & set(contradicting):
            raise ValueError(
                "A source cannot both support and contradict a claim"
            )

        positions = {
            item.source_id: item.position
            for item in self.source_assessments
        }

        for source_id in supporting:
            if positions[source_id] != EvidencePosition.SUPPORTS:
                raise ValueError(
                    "Supporting source position does not match assessment"
                )

        for source_id in contradicting:
            if positions[source_id] != EvidencePosition.CONTRADICTS:
                raise ValueError(
                    "Contradicting source position does not match assessment"
                )

        return self

# --------------------------------------------------
# CRITIQUE AGENT CONTRACTS
# --------------------------------------------------

class CritiqueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CritiqueIssueType(str, Enum):
    SOURCE_RELIABILITY = "source_reliability"
    SOURCE_INDEPENDENCE = "source_independence"
    MISSING_COUNTEREVIDENCE = "missing_counterevidence"
    CLAIM_INTERPRETATION = "claim_interpretation"
    TEMPORAL_CONTEXT = "temporal_context"
    REASONING_GAP = "reasoning_gap"
    CONFIDENCE_CALIBRATION = "confidence_calibration"
    CITATION_PROBLEM = "citation_problem"


class CritiqueAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    round_number: int = Field(ge=1, le=2)
    verification: VerificationAgentResult
    sources: list[ResearchSource]


class CritiqueFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objection_id: str
    claim_id: str
    issue_type: CritiqueIssueType
    severity: CritiqueSeverity
    objection: str
    source_ids: list[str] = Field(default_factory=list)
    requires_reassessment: bool = False

    @model_validator(mode="after")
    def validate_source_ids(self):
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Duplicate source IDs in critique finding")
        return self


class CritiqueAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    round_number: int = Field(ge=1, le=2)
    findings: list[CritiqueFinding]
    agrees_with_verdict: bool
    alternative_verdict: Optional[VerificationStatus] = None
    summary: str
    requires_human_review: bool = True

    @model_validator(mode="after")
    def validate_findings(self):
        finding_ids = [
            finding.objection_id for finding in self.findings
        ]

        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("Duplicate critique finding IDs")

        if any(
            finding.claim_id != self.claim_id
            for finding in self.findings
        ):
            raise ValueError("Finding claim IDs do not match result")

        if self.agrees_with_verdict and self.alternative_verdict:
            raise ValueError(
                "An agreeing critique cannot propose an alternative verdict"
            )

        if not self.agrees_with_verdict and not self.alternative_verdict:
            raise ValueError(
                "A disagreement must propose an alternative verdict"
            )

        if not self.requires_human_review:
            raise ValueError(
                "Critique Agent cannot bypass human review"
            )

        return self

class DecisionAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    verification: VerificationAgentResult
    critique: CritiqueAgentResult
    sources: list[ResearchSource]


class DecisionAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    verdict: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)

    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    considered_objection_ids: list[str] = Field(default_factory=list)

    reasoning: str
    summary: str

    requires_reassessment: bool = False
    requires_human_review: bool = True

    @model_validator(mode="after")
    def validate_decision(self):
        if not self.claim_id.strip():
            raise ValueError("claim_id cannot be empty")

        if not self.reasoning.strip():
            raise ValueError("reasoning cannot be empty")

        if not self.summary.strip():
            raise ValueError("summary cannot be empty")

        if len(self.supporting_source_ids) != len(set(self.supporting_source_ids)):
            raise ValueError("Duplicate supporting source IDs")

        if len(self.contradicting_source_ids) != len(set(self.contradicting_source_ids)):
            raise ValueError("Duplicate contradicting source IDs")

        if len(self.considered_objection_ids) != len(set(self.considered_objection_ids)):
            raise ValueError("Duplicate objection IDs")

        overlap = set(self.supporting_source_ids) & set(self.contradicting_source_ids)
        if overlap:
            raise ValueError("A source cannot both support and contradict the claim")

        if not self.requires_human_review:
            raise ValueError("Human review must always be required")

        return self
