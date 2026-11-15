import json

import app.orchestrator.verification_orchestrator as orchestrator

from app.schemas.verification import (
    PlannerInput,
    ResearchSource,
    VerificationResult,
)


# ---------------------------------------------------------
# Test proposal
# ---------------------------------------------------------

proposal = PlannerInput(
    proposal_id="proposal_e2e_001",
    article_title="Helsinki",
    language_code="en",
    edit_summary="Update capital information",
    old_text="Helsinki is a city in Finland.",
    proposed_text="Helsinki is the capital of Finland.",
)


# ---------------------------------------------------------
# Mock evidence gathering only.
# The actual agent prompts and parsers remain active.
# ---------------------------------------------------------

source = ResearchSource(
    source_id="source_e2e_001",
    title="Test reference",
    url="https://example.com/helsinki",
    content="Helsinki is the capital of Finland.",
    retrieved_at="2026-11-14T12:00:00+00:00",
)


planned_task_types = []


def fake_gather_planned_evidence(**kwargs):
    planned_task_types.extend(
        task.task_type.value for task in kwargs["tasks"]
    )
    return [source], None, None, []


orchestrator._gather_planned_evidence = fake_gather_planned_evidence


# ---------------------------------------------------------
# Mock LLM provider.
# Each response is parsed by the actual agent parser.
# ---------------------------------------------------------

agent_calls = []


def mock_model_call(agent_name, prompt):
    agent_calls.append(agent_name)

    if agent_name == "planner":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "objective": "Verify the capital claim.",
            "tasks": [
                {
                    "task_id": "task_001",
                    "task_type": "extract_claims",
                    "rationale": "Extract factual claims.",
                    "priority": 5,
                    "required": True,
                },
                {
                    "task_id": "task_002",
                    "task_type": "internal_retrieval",
                    "rationale": "Retrieve internal evidence.",
                    "priority": 4,
                    "required": True,
                },
                {
                    "task_id": "task_003",
                    "task_type": "external_research",
                    "rationale": "Find external evidence.",
                    "priority": 5,
                    "required": True,
                },
            ],
            "max_critique_rounds": 2,
            "rationale": "Verify the factual claim.",
        })

    if agent_name == "claim_extractor":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "claims": [
                {
                    "claim_id": "claim_e2e_001",
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
            "claim_id": "claim_e2e_001",
            "verdict": "supported",
            "confidence": 0.90,
            "source_assessments": [
                {
                    "source_id": source.source_id,
                    "position": "supports",
                    "relevance": 0.95,
                    "reasoning": "The source directly confirms the claim.",
                    "quoted_excerpt": "Helsinki is the capital of Finland.",
                    "limitations": [],
                }
            ],
            "supporting_source_ids": [source.source_id],
            "contradicting_source_ids": [],
            "reasoning": "The evidence directly supports the claim.",
            "caveats": [],
            "requires_human_review": True,
        })

    if agent_name == "critique_agent":
        return json.dumps({
            "claim_id": "claim_e2e_001",
            "round_number": 1,
            "findings": [],
            "agrees_with_verdict": True,
            "alternative_verdict": None,
            "summary": "No material objections identified.",
            "requires_human_review": True,
        })

    if agent_name == "decision_agent":
        return json.dumps({
            "claim_id": "claim_e2e_001",
            "verdict": "supported",
            "confidence": 0.90,
            "supporting_source_ids": [source.source_id],
            "contradicting_source_ids": [],
            "considered_objection_ids": [],
            "reasoning": "The available evidence supports the claim.",
            "summary": "Claim supported.",
            "requires_reassessment": False,
            "requires_human_review": True,
        })

    raise ValueError(f"Unexpected agent: {agent_name}")


# ---------------------------------------------------------
# Mock embedding provider.
# Evidence retrieval is mocked, so this is not used.
# ---------------------------------------------------------

def mock_embed_text(text):
    return [0.0] * 1024


# ---------------------------------------------------------
# Execute workflow
# ---------------------------------------------------------

result = orchestrator.run_verification(
    proposal=proposal,
    connection=None,
    model_call=mock_model_call,
    embed_text=mock_embed_text,
)


# ---------------------------------------------------------
# Assertions
# ---------------------------------------------------------

assert isinstance(result, VerificationResult)
assert result.proposal_id == proposal.proposal_id
assert result.requires_human_review is True
assert len(result.decisions) == 1

decision = result.decisions[0]

assert decision.claim_id == "claim_e2e_001"
assert decision.verdict.value == "supported"
assert decision.confidence == 0.90
assert decision.supporting_evidence == [source.source_id]
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

assert planned_task_types == [
    "extract_claims",
    "internal_retrieval",
    "external_research",
]
assert result.warnings == []

print("END-TO-END ORCHESTRATOR TEST: SUCCESS")
print("Agent sequence:", " -> ".join(agent_calls))
print("Claims processed:", len(result.decisions))
print("Final verdict:", decision.verdict.value)
print("Confidence:", decision.confidence)
print("Human review required:", result.requires_human_review)
print("Evidence traceability: SUCCESS")
