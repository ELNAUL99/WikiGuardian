import json

from app.agents.decision_agent import (
    DECISION_SYSTEM_PROMPT,
    build_decision_prompt,
    parse_decision_output,
)
from app.schemas.verification import (
    AgentStatus,
    CritiqueAgentResult,
    CritiqueFinding,
    CritiqueIssueType,
    CritiqueSeverity,
    DecisionAgentInput,
    EvidencePosition,
    ResearchSource,
    SourceAssessment,
    VerificationAgentResult,
    VerificationStatus,
)


sources = [
    ResearchSource(
        source_id="oxy_visit_finland",
        title="Visit Finland",
        url="https://www.visitfinland.com/",
        search_snippet="Information about Finland.",
        content="Helsinki is the capital of Finland.",
        search_position=1,
        source_date=None,
        retrieved_at="2026-11-14T12:00:00Z",
    ),
    ResearchSource(
        source_id="oxy_mappr",
        title="Mappr",
        url="https://www.mappr.co/",
        search_snippet="Geographical information about Finland.",
        content="The capital city of Finland is Helsinki.",
        search_position=2,
        source_date=None,
        retrieved_at="2026-11-14T12:00:00Z",
    ),
]

verification = VerificationAgentResult(
    claim_id="claim_001",
    verdict=VerificationStatus.SUPPORTED,
    confidence=0.90,
    source_assessments=[
        SourceAssessment(
            source_id="oxy_visit_finland",
            position=EvidencePosition.SUPPORTS,
            relevance=0.95,
            reasoning="The source explicitly identifies Helsinki as the capital.",
            quoted_excerpt="Helsinki is the capital of Finland.",
            limitations=["Source independence has not been established."],
        ),
        SourceAssessment(
            source_id="oxy_mappr",
            position=EvidencePosition.SUPPORTS,
            relevance=0.90,
            reasoning="The source also identifies Helsinki as the capital.",
            quoted_excerpt="The capital city of Finland is Helsinki.",
            limitations=["Source independence has not been established."],
        ),
    ],
    supporting_source_ids=["oxy_visit_finland", "oxy_mappr"],
    contradicting_source_ids=[],
    reasoning="Both sources support the claim.",
    caveats=["Source independence should be examined."],
    requires_human_review=True,
)

critique = CritiqueAgentResult(
    claim_id="claim_001",
    round_number=1,
    findings=[
        CritiqueFinding(
            objection_id="objection_001",
            claim_id="claim_001",
            issue_type=CritiqueIssueType.SOURCE_INDEPENDENCE,
            severity=CritiqueSeverity.MEDIUM,
            objection="The two sources may not be independent.",
            source_ids=["oxy_visit_finland", "oxy_mappr"],
            requires_reassessment=False,
        ),
        CritiqueFinding(
            objection_id="objection_002",
            claim_id="claim_001",
            issue_type=CritiqueIssueType.SOURCE_RELIABILITY,
            severity=CritiqueSeverity.LOW,
            objection="The reliability of the second source should be considered.",
            source_ids=["oxy_mappr"],
            requires_reassessment=False,
        ),
    ],
    agrees_with_verdict=True,
    alternative_verdict=None,
    summary="The verdict is plausible, but source independence needs consideration.",
    requires_human_review=True,
)

request = DecisionAgentInput(
    claim_id="claim_001",
    claim_text="Helsinki is the capital of Finland.",
    verification=verification,
    critique=critique,
    sources=sources,
)

raw_decision = {
    "claim_id": "claim_001",
    "verdict": "supported",
    "confidence": 0.82,
    "supporting_source_ids": ["oxy_visit_finland", "oxy_mappr"],
    "contradicting_source_ids": [],
    "considered_objection_ids": ["objection_001", "objection_002"],
    "reasoning": (
        "Both sources support the claim. However, their independence is "
        "not established, so confidence is lower than the original assessment."
    ),
    "summary": "The claim is supported, subject to human review.",
    "requires_reassessment": False,
    "requires_human_review": True,
}

prompt = build_decision_prompt(request)
assert "Helsinki is the capital of Finland." in prompt
assert "objection_001" in prompt
assert "independence" in DECISION_SYSTEM_PROMPT.lower()
print("DECISION PROMPT TEST: SUCCESS")

result = parse_decision_output(json.dumps(raw_decision), request)
assert result.verdict == VerificationStatus.SUPPORTED
assert result.confidence == 0.82
print("DECISION PARSER TEST: SUCCESS")

assert set(result.supporting_source_ids).issubset(
    {source.source_id for source in sources}
)
assert set(result.considered_objection_ids) == {
    finding.objection_id for finding in critique.findings
}
print("SOURCE AND OBJECTION TRACEABILITY TEST: SUCCESS")

assert result.requires_human_review is True
print("HUMAN REVIEW ENFORCEMENT: SUCCESS")

invalid_decision = dict(raw_decision)
invalid_decision["supporting_source_ids"] = ["unknown_source"]

try:
    parse_decision_output(json.dumps(invalid_decision), request)
    raise AssertionError("Unknown source ID should have been rejected.")
except ValueError as exc:
    assert "unknown source" in str(exc).lower()

print("UNKNOWN SOURCE REJECTION TEST: SUCCESS")

print("\nFinal verdict:", result.verdict.value)
print("Confidence:", result.confidence)
print("Supporting sources:", len(result.supporting_source_ids))
print("Considered objections:", len(result.considered_objection_ids))
print("Human review required:", result.requires_human_review)

# Zero-source decision safeguards
empty_sources_request = request.model_copy(update={"sources": []})

for forbidden_verdict in (
    VerificationStatus.SUPPORTED,
    VerificationStatus.CONTRADICTED,
):
    invalid_zero_source_decision = dict(raw_decision)
    invalid_zero_source_decision["verdict"] = forbidden_verdict.value
    invalid_zero_source_decision["supporting_source_ids"] = []
    invalid_zero_source_decision["contradicting_source_ids"] = []
    invalid_zero_source_decision["confidence"] = 0.50

    try:
        parse_decision_output(
            json.dumps(invalid_zero_source_decision),
            empty_sources_request,
        )
        raise AssertionError(
            f"{forbidden_verdict.value} must be rejected without evidence."
        )
    except ValueError as exc:
        assert "without evidence sources" in str(exc).lower()

print("ZERO-SOURCE SUPPORTED VERDICT REJECTION: SUCCESS")
print("ZERO-SOURCE CONTRADICTED VERDICT REJECTION: SUCCESS")

valid_zero_source_decision = dict(raw_decision)
valid_zero_source_decision["verdict"] = (
    VerificationStatus.INSUFFICIENT_EVIDENCE.value
)
valid_zero_source_decision["supporting_source_ids"] = []
valid_zero_source_decision["contradicting_source_ids"] = []
valid_zero_source_decision["confidence"] = 0.0
valid_zero_source_decision["reasoning"] = (
    "No evidence sources were available to assess the claim."
)
valid_zero_source_decision["summary"] = (
    "There is insufficient evidence to determine the claim."
)
valid_zero_source_decision["considered_objection_ids"] = []

empty_verification = verification.model_copy(
    update={
        "verdict": VerificationStatus.INSUFFICIENT_EVIDENCE,
        "confidence": 0.0,
        "source_assessments": [],
        "supporting_source_ids": [],
        "contradicting_source_ids": [],
        "reasoning": "No evidence sources were available.",
    }
)

empty_critique = critique.model_copy(
    update={
        "findings": [],
        "agrees_with_verdict": True,
        "alternative_verdict": None,
    }
)

empty_sources_request = request.model_copy(
    update={
        "verification": empty_verification,
        "critique": empty_critique,
        "sources": [],
    }
)

zero_source_result = parse_decision_output(
    json.dumps(valid_zero_source_decision),
    empty_sources_request,
)

assert zero_source_result.verdict == VerificationStatus.INSUFFICIENT_EVIDENCE
assert zero_source_result.supporting_source_ids == []
assert zero_source_result.contradicting_source_ids == []
assert zero_source_result.requires_human_review is True

print("ZERO-SOURCE INSUFFICIENT EVIDENCE ACCEPTANCE: SUCCESS")

