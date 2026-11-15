import json

from app.orchestrator.verification_orchestrator import run_verification
from app.schemas.verification import (
    PlannerInput,
    VerificationResult,
)


# ---------------------------------------------------------
# Test proposal
# ---------------------------------------------------------

proposal = PlannerInput(
    proposal_id="proposal_no_evidence",
    article_title="Helsinki",
    language_code="en",
    edit_summary="Update capital information",
    old_text="Helsinki is a city in Finland.",
    proposed_text="Helsinki is the capital of Finland.",
)


# ---------------------------------------------------------
# Mock LLM provider.
# All actual agent parsers remain active.
# ---------------------------------------------------------

agent_calls = []


def mock_model_call(agent_name, prompt):
    agent_calls.append(agent_name)

    if agent_name == "planner":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "objective": "Extract and assess the proposed factual claim.",
            "tasks": [
                {
                    "task_id": "task_001",
                    "task_type": "extract_claims",
                    "rationale": "Claim extraction is always required.",
                    "priority": 5,
                    "required": True,
                }
            ],
            "max_critique_rounds": 2,
            "rationale": "No additional evidence retrieval was selected.",
        })

    if agent_name == "claim_extractor":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "claims": [
                {
                    "claim_id": "claim_no_evidence",
                    "claim_text": "Helsinki is the capital of Finland.",
                    "subject": "Helsinki",
                    "predicate": "is the capital of",
                    "object": "Finland",
                    "context": "Political status",
                    "source_text": "Helsinki is the capital of Finland.",
                }
            ],
            "extraction_summary": "One factual claim extracted.",
        })

    if agent_name == "verification_agent":
        return json.dumps({
            "claim_id": "claim_no_evidence",
            "verdict": "insufficient_evidence",
            "confidence": 0.0,
            "source_assessments": [],
            "supporting_source_ids": [],
            "contradicting_source_ids": [],
            "reasoning": (
                "No evidence sources were supplied for assessment."
            ),
            "caveats": ["No evidence retrieval was performed."],
            "requires_human_review": True,
        })

    if agent_name == "critique_agent":
        return json.dumps({
            "claim_id": "claim_no_evidence",
            "round_number": 1,
            "findings": [],
            "agrees_with_verdict": True,
            "alternative_verdict": None,
            "summary": (
                "The insufficient-evidence verdict is appropriate "
                "because no sources were available."
            ),
            "requires_human_review": True,
        })

    if agent_name == "decision_agent":
        return json.dumps({
            "claim_id": "claim_no_evidence",
            "verdict": "insufficient_evidence",
            "confidence": 0.0,
            "supporting_source_ids": [],
            "contradicting_source_ids": [],
            "considered_objection_ids": [],
            "reasoning": (
                "No evidence was available to support or contradict "
                "the claim."
            ),
            "summary": "Insufficient evidence to verify the claim.",
            "requires_reassessment": False,
            "requires_human_review": True,
        })

    raise ValueError(f"Unexpected agent: {agent_name}")


# ---------------------------------------------------------
# Embedding provider.
# It must never be called because retrieval was not selected.
# ---------------------------------------------------------

def unexpected_embedding_call(text):
    raise AssertionError(
        "Embedding provider was called despite no retrieval task."
    )


# ---------------------------------------------------------
# Execute the real orchestrator.
# No evidence gathering functions are mocked.
# ---------------------------------------------------------

result = run_verification(
    proposal=proposal,
    connection=None,
    model_call=mock_model_call,
    embed_text=unexpected_embedding_call,
)


# ---------------------------------------------------------
# Assertions
# ---------------------------------------------------------

assert isinstance(result, VerificationResult)
assert result.proposal_id == proposal.proposal_id
assert result.requires_human_review is True
assert len(result.decisions) == 1

decision = result.decisions[0]

assert decision.claim_id == "claim_no_evidence"
assert decision.verdict.value == "insufficient_evidence"
assert decision.supporting_evidence == []
assert decision.contradicting_evidence == []
assert decision.requires_human_review is True

expected_calls = [
    "planner",
    "claim_extractor",
    "verification_agent",
    "critique_agent",
    "decision_agent",
]

assert agent_calls == expected_calls, (
    f"Unexpected agent sequence: {agent_calls}"
)

assert result.warnings
assert any(
    "no available evidence-gathering tasks" in warning
    for warning in result.warnings
)

print("NO-EVIDENCE END-TO-END WORKFLOW: SUCCESS")
print("Agent sequence:", " -> ".join(agent_calls))
print("Claims processed:", len(result.decisions))
print("Evidence sources: 0")
print("Final verdict:", decision.verdict.value)
print("Supporting evidence:", len(decision.supporting_evidence))
print("Human review required:", result.requires_human_review)
print("Planner warning recorded: SUCCESS")
