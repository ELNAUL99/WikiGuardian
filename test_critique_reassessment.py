import json

import app.orchestrator.verification_orchestrator as orchestrator

from app.schemas.verification import (
    PlannerInput,
    ResearchSource,
)


proposal = PlannerInput(
    proposal_id="proposal_critique_001",
    article_title="Helsinki",
    language_code="en",
    edit_summary="Update capital information",
    old_text="Helsinki is a city in Finland.",
    proposed_text="Helsinki is the capital of Finland.",
)

source = ResearchSource(
    source_id="source_critique_001",
    title="Test reference",
    url="https://example.com/helsinki",
    content="Helsinki is the capital of Finland.",
    retrieved_at="2026-11-14T12:00:00+00:00",
)


def fake_gather_planned_evidence(**kwargs):
    return [source], None, None, []


orchestrator._gather_planned_evidence = fake_gather_planned_evidence


agent_calls = []
verification_count = 0
critique_count = 0
reassessment_prompt_detected = False


def mock_model_call(agent_name, prompt):
    global verification_count, critique_count
    global reassessment_prompt_detected

    agent_calls.append(agent_name)

    if agent_name == "planner":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "objective": "Verify the capital claim.",
            "tasks": [
                {
                    "task_id": "task_001",
                    "task_type": "extract_claims",
                    "rationale": "Extract claims.",
                    "priority": 5,
                    "required": True,
                },
                {
                    "task_id": "task_002",
                    "task_type": "external_research",
                    "rationale": "Retrieve the source used in this test.",
                    "priority": 5,
                    "required": True,
                }
            ],
            "max_critique_rounds": 2,
            "rationale": "Test adversarial review.",
        })

    if agent_name == "claim_extractor":
        return json.dumps({
            "proposal_id": proposal.proposal_id,
            "claims": [
                {
                    "claim_id": "claim_critique_001",
                    "claim_text": "Helsinki is the capital of Finland.",
                    "subject": "Helsinki",
                    "predicate": "is the capital of",
                    "object": "Finland",
                    "context": "Political status",
                    "source_text": "Helsinki is the capital of Finland.",
                }
            ],
            "extraction_summary": "One claim extracted.",
        })

    if agent_name == "verification_agent":
        verification_count += 1

        if verification_count == 1:
            return json.dumps({
                "claim_id": "claim_critique_001",
                "verdict": "supported",
                "confidence": 0.90,
                "source_assessments": [
                    {
                        "source_id": source.source_id,
                        "position": "supports",
                        "relevance": 0.95,
                        "reasoning": "The source directly supports the claim.",
                        "quoted_excerpt": "Helsinki is the capital of Finland.",
                        "limitations": [],
                    }
                ],
                "supporting_source_ids": [source.source_id],
                "contradicting_source_ids": [],
                "reasoning": "Initial assessment supports the claim.",
                "caveats": [],
                "requires_human_review": True,
            })

        reassessment_prompt_detected = (
            "ADDITIONAL REASSESSMENT INSTRUCTIONS" in prompt
        )

        return json.dumps({
            "claim_id": "claim_critique_001",
            "verdict": "insufficient_evidence",
            "confidence": 0.50,
            "source_assessments": [
                {
                    "source_id": source.source_id,
                    "position": "neutral",
                    "relevance": 0.20,
                    "reasoning": (
                        "The source reliability concern prevents "
                        "a confident factual assessment."
                    ),
                    "quoted_excerpt": "Helsinki is the capital of Finland.",
                    "limitations": ["Source reliability is uncertain."],
                }
            ],
            "supporting_source_ids": [],
            "contradicting_source_ids": [],
            "reasoning": "The original assessment was too confident.",
            "caveats": ["Independent confirmation is insufficient."],
            "requires_human_review": True,
        })

    if agent_name == "critique_agent":
        critique_count += 1

        if critique_count == 1:
            return json.dumps({
                "claim_id": "claim_critique_001",
                "round_number": 1,
                "findings": [
                    {
                        "objection_id": "objection_critique_001",
                        "claim_id": "claim_critique_001",
                        "issue_type": "source_reliability",
                        "severity": "high",
                        "objection": (
                            "The source reliability is not established."
                        ),
                        "source_ids": [source.source_id],
                        "requires_reassessment": True,
                    }
                ],
                "agrees_with_verdict": False,
                "alternative_verdict": "insufficient_evidence",
                "summary": "A serious reliability issue was identified.",
                "requires_human_review": True,
            })

        return json.dumps({
            "claim_id": "claim_critique_001",
            "round_number": 2,
            "findings": [],
            "agrees_with_verdict": True,
            "alternative_verdict": None,
            "summary": "The reassessment addressed the objection.",
            "requires_human_review": True,
        })

    if agent_name == "decision_agent":
        return json.dumps({
            "claim_id": "claim_critique_001",
            "verdict": "insufficient_evidence",
            "confidence": 0.55,
            "supporting_source_ids": [],
            "contradicting_source_ids": [],
            "considered_objection_ids": [
                "objection_critique_001"
            ],
            "reasoning": (
                "The initial assessment was challenged. "
                "The reassessment found insufficient evidence."
            ),
            "summary": "Insufficient evidence after reassessment.",
            "requires_reassessment": True,
            "requires_human_review": True,
        })

    raise ValueError(f"Unexpected agent: {agent_name}")


result = orchestrator.run_verification(
    proposal=proposal,
    connection=None,
    model_call=mock_model_call,
    embed_text=lambda text: [0.0] * 1024,
)

decision = result.decisions[0]

assert verification_count == 2
assert critique_count == 2
assert reassessment_prompt_detected is True

assert decision.verdict.value == "insufficient_evidence"
assert decision.confidence <= 0.60
assert "objection_critique_001" in decision.critique_objections
assert decision.requires_human_review is True
assert result.requires_human_review is True
assert result.warnings == []

print("ADVERSARIAL CRITIQUE TEST: SUCCESS")
print("Verification passes:", verification_count)
print("Critique rounds:", critique_count)
print("Reassessment prompt detected:", reassessment_prompt_detected)
print("Final verdict:", decision.verdict.value)
print("Final confidence:", decision.confidence)
print("Critique objection preserved:", decision.critique_objections)
print("Human review required:", result.requires_human_review)
