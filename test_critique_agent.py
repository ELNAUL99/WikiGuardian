import json

from app.schemas.verification import (
    ResearchSource,
    VerificationAgentResult,
    CritiqueAgentInput,
    VerificationStatus,
)

from app.agents.critique_agent import (
    CRITIQUE_SYSTEM_PROMPT,
    build_critique_prompt,
    parse_critique_output,
)


sources = [
    ResearchSource(
        source_id="oxy_visit_finland",
        title="Discover Helsinki | Visit Finland",
        url="https://www.visitfinland.com/",
        content=(
            "Helsinki is a charming seaside city. "
            "Helsinki is the capital of Finland."
        ),
        retrieved_at="2026-11-14T13:00:00Z",
    ),
    ResearchSource(
        source_id="oxy_mappr",
        title="What is the Capital of Finland? | Mappr",
        url="https://www.mappr.co/capital-cities/finland/",
        content=(
            "Helsinki is the capital of Finland. "
            "It is also the most populous city."
        ),
        retrieved_at="2026-11-14T13:00:00Z",
    ),
]

verification = VerificationAgentResult(
    claim_id="claim_test_001",
    verdict=VerificationStatus.SUPPORTED,
    confidence=0.90,
    source_assessments=[
        {
            "source_id": "oxy_visit_finland",
            "position": "supports",
            "relevance": 1.0,
            "reasoning": "Explicitly supports the claim.",
            "quoted_excerpt": "Helsinki is the capital of Finland.",
            "limitations": ["Tourism-oriented source."],
        },
        {
            "source_id": "oxy_mappr",
            "position": "supports",
            "relevance": 1.0,
            "reasoning": "Explicitly supports the claim.",
            "quoted_excerpt": "Helsinki is the capital of Finland.",
            "limitations": ["Secondary informational source."],
        },
    ],
    supporting_source_ids=[
        "oxy_visit_finland",
        "oxy_mappr",
    ],
    contradicting_source_ids=[],
    reasoning="Both sources explicitly support the claim.",
    requires_human_review=True,
)

request = CritiqueAgentInput(
    claim_id="claim_test_001",
    claim_text="Helsinki is the capital of Finland.",
    round_number=1,
    verification=verification,
    sources=sources,
)

mock_response = {
    "claim_id": "claim_test_001",
    "round_number": 1,
    "findings": [
        {
            "objection_id": "objection_001",
            "claim_id": "claim_test_001",
            "issue_type": "source_independence",
            "severity": "medium",
            "objection": (
                "Both sources support the claim, but their "
                "independence has not been established. "
                "Two agreeing websites should not automatically "
                "be treated as two independent confirmations."
            ),
            "source_ids": [
                "oxy_visit_finland",
                "oxy_mappr",
            ],
            "requires_reassessment": False,
        },
        {
            "objection_id": "objection_002",
            "claim_id": "claim_test_001",
            "issue_type": "source_reliability",
            "severity": "low",
            "objection": (
                "The Visit Finland page is tourism-oriented. "
                "Its statement is relevant, but an official "
                "government source would provide stronger "
                "institutional authority."
            ),
            "source_ids": [
                "oxy_visit_finland",
            ],
            "requires_reassessment": False,
        },
    ],
    "agrees_with_verdict": True,
    "alternative_verdict": None,
    "summary": (
        "The supported verdict is reasonable, but source "
        "independence and authority remain limitations."
    ),
    "requires_human_review": True,
}

prompt = build_critique_prompt(request)

result = parse_critique_output(
    json.dumps(mock_response),
    request,
)

assert CRITIQUE_SYSTEM_PROMPT
assert "INPUT DATA" in prompt
assert result.claim_id == verification.claim_id
assert result.round_number == 1
assert len(result.findings) == 2
assert result.agrees_with_verdict
assert result.requires_human_review

print("CRITIQUE PROMPT TEST: SUCCESS")
print("CRITIQUE PARSER TEST: SUCCESS")
print("SOURCE TRACEABILITY TEST: SUCCESS")
print("ROUND VALIDATION TEST: SUCCESS")
print("Human review enforcement: SUCCESS")

print("\nFindings:", len(result.findings))

for finding in result.findings:
    print(
        f"- {finding.issue_type.value}: "
        f"{finding.severity.value}"
    )

print("\nAgrees with original verdict:", result.agrees_with_verdict)
