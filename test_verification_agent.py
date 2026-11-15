import json

from app.schemas.verification import (
    ResearchSource,
    VerificationAgentInput,
    VerificationStatus,
)

from app.agents.verification_agent import (
    VERIFICATION_SYSTEM_PROMPT,
    build_verification_prompt,
    parse_verification_output,
)


sources = [
    ResearchSource(
        source_id="oxy_visit_finland",
        title="Discover Helsinki | Visit Finland",
        url="https://www.visitfinland.com/en/places-to-go/helsinki-region/helsinki-city/",
        content=(
            "Helsinki is a charming seaside city. "
            "Helsinki is the capital of Finland."
        ),
        search_position=1,
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
        search_position=2,
        retrieved_at="2026-11-14T13:00:00Z",
    ),
]

request = VerificationAgentInput(
    claim_id="claim_test_001",
    claim_text="Helsinki is the capital of Finland.",
    sources=sources,
)

mock_response = {
    "claim_id": "claim_test_001",
    "verdict": "supported",
    "confidence": 0.90,
    "source_assessments": [
        {
            "source_id": "oxy_visit_finland",
            "position": "supports",
            "relevance": 1.0,
            "reasoning": "The source explicitly identifies Helsinki as the capital.",
            "quoted_excerpt": "Helsinki is the capital of Finland.",
            "limitations": [
                "The page is a tourism source."
            ],
        },
        {
            "source_id": "oxy_mappr",
            "position": "supports",
            "relevance": 1.0,
            "reasoning": "The source explicitly states the claim.",
            "quoted_excerpt": "Helsinki is the capital of Finland.",
            "limitations": [
                "The source's editorial authority has not been independently assessed."
            ],
        },
    ],
    "supporting_source_ids": [
        "oxy_visit_finland",
        "oxy_mappr",
    ],
    "contradicting_source_ids": [],
    "reasoning": (
        "Both supplied sources explicitly support the claim."
    ),
    "caveats": [
        "This is a simulated assessment, not a live LLM verdict."
    ],
    "requires_human_review": True,
}

prompt = build_verification_prompt(request)

result = parse_verification_output(
    json.dumps(mock_response),
    request,
)

assert VERIFICATION_SYSTEM_PROMPT
assert "INPUT DATA" in prompt
assert result.verdict == VerificationStatus.SUPPORTED
assert len(result.supporting_source_ids) == 2
assert result.requires_human_review is True

print("VERIFICATION PROMPT TEST: SUCCESS")
print("VERIFICATION PARSER TEST: SUCCESS")
print("SOURCE TRACEABILITY TEST: SUCCESS")
print("Human review enforcement: SUCCESS")
print("\nVerdict:", result.verdict.value)
print("Confidence:", result.confidence)
print("Supporting sources:", len(result.supporting_source_ids))


# ---------------------------------------------------------
# ZERO-SOURCE VERDICT SAFEGUARDS
# ---------------------------------------------------------

empty_request = VerificationAgentInput(
    claim_id="claim_test_001",
    claim_text="Helsinki is the capital of Finland.",
    sources=[],
)


def make_empty_source_response(verdict):
    response = dict(mock_response)
    response.update({
        "verdict": verdict,
        "confidence": 0.0,
        "source_assessments": [],
        "supporting_source_ids": [],
        "contradicting_source_ids": [],
        "reasoning": "No evidence sources were available.",
        "caveats": ["No evidence was retrieved."],
    })
    return response


for invalid_verdict in ("supported", "contradicted"):
    rejected = False

    try:
        parse_verification_output(
            json.dumps(make_empty_source_response(invalid_verdict)),
            empty_request,
        )
    except ValueError as exc:
        rejected = "without evidence sources" in str(exc)

    assert rejected, (
        f"Zero-source {invalid_verdict} verdict was not rejected."
    )

print("ZERO-SOURCE SUPPORTED VERDICT REJECTION: SUCCESS")
print("ZERO-SOURCE CONTRADICTED VERDICT REJECTION: SUCCESS")


empty_result = parse_verification_output(
    json.dumps(
        make_empty_source_response("insufficient_evidence")
    ),
    empty_request,
)

assert empty_result.verdict == VerificationStatus.INSUFFICIENT_EVIDENCE
assert empty_result.source_assessments == []
assert empty_result.supporting_source_ids == []
assert empty_result.contradicting_source_ids == []
assert empty_result.requires_human_review is True

print("ZERO-SOURCE INSUFFICIENT EVIDENCE ACCEPTANCE: SUCCESS")
