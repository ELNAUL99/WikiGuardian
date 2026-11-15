from app.schemas.verification import PlannerInput
from app.agents.planner import (
    PLANNER_SYSTEM_PROMPT,
    build_planner_prompt,
    parse_planner_output,
)

proposal = PlannerInput(
    proposal_id="proposal_001",
    article_title="Helsinki",
    language_code="en",
    edit_summary="Updating population information",
    old_text="Helsinki has a population of 650000.",
    proposed_text="Helsinki has a population of 700000.",
)

mock_response = """
{
    "proposal_id": "proposal_001",
    "objective": "Verify the updated population figure.",
    "tasks": [
        {
            "task_id": "task_001",
            "task_type": "extract_claims",
            "rationale": "Identify the factual population claim.",
            "priority": 5,
            "required": true
        },
        {
            "task_id": "task_002",
            "task_type": "internal_retrieval",
            "rationale": "Find relevant Wikipedia information.",
            "priority": 4,
            "required": true
        },
        {
            "task_id": "task_003",
            "task_type": "external_research",
            "rationale": "Find independent population sources.",
            "priority": 5,
            "required": true
        },
        {
            "task_id": "task_004",
            "task_type": "historical_review",
            "rationale": "Compare the proposed figure with previous revisions.",
            "priority": 3,
            "required": false
        }
    ],
    "max_critique_rounds": 2,
    "rationale": "Population figures require reliable and current evidence."
}
"""

prompt = build_planner_prompt(proposal)
plan = parse_planner_output(mock_response, proposal)

print("PLANNER TEST: SUCCESS")
print("\nSystem prompt available:", bool(PLANNER_SYSTEM_PROMPT))
print("User prompt generated:", bool(prompt))
print("\nVerification plan:")
print(plan.model_dump_json(indent=2))
