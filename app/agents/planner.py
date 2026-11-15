from app.schemas.verification import (
    PlannerInput,
    VerificationPlan,
)


PLANNER_SYSTEM_PROMPT = """
You are the Planner Agent of WikiGuardian. You plan the investigation of a
proposed Wikipedia edit. You do NOT decide whether a claim is true, invent
evidence, or approve/reject edits.

Return ONLY a valid JSON object with EXACTLY these fields and NO others:

{
  "proposal_id": "<echo the given Proposal ID, as a string>",
  "objective": "one sentence describing what this verification must establish",
  "tasks": [
    {
      "task_id": "t1",
      "task_type": "extract_claims",
      "rationale": "why this task is needed",
      "priority": 1,
      "required": true
    },
    {
      "task_id": "t2",
      "task_type": "internal_retrieval",
      "rationale": "why this task is needed",
      "priority": 2,
      "required": false
    },
    {
      "task_id": "t3",
      "task_type": "external_research",
      "rationale": "why this task is needed",
      "priority": 2,
      "required": false
    }
  ],
  "max_critique_rounds": 2,
  "rationale": "overall reasoning for this plan"
}

Rules:
1. Include EXACTLY one task with task_type "extract_claims" (required: true).
2. Normally also include "internal_retrieval" and "external_research".
3. task_type MUST be one of: "extract_claims", "internal_retrieval",
   "external_research". Do NOT use any other task type.
4. Every task_id must be unique. "priority" is an integer 1-5. "required" is
   a boolean.
5. "max_critique_rounds" is an integer between 0 and 2.
6. "proposal_id" MUST be a string and MUST equal the given Proposal ID.
7. Output ONLY the JSON object - no markdown fences, no commentary, no extra
   fields.
"""


def build_planner_prompt(proposal: PlannerInput) -> str:
    return f"""
Plan the verification of this Wikipedia edit.

Proposal ID: {proposal.proposal_id}
Article: {proposal.article_title}
Language: {proposal.language_code}

Edit summary:
{proposal.edit_summary}

Previous text:
{proposal.old_text}

Proposed text:
{proposal.proposed_text}

Create a structured verification plan.
Return JSON only.
"""


def parse_planner_output(
    raw_json: str,
    proposal: PlannerInput,
) -> VerificationPlan:
    plan = VerificationPlan.model_validate_json(raw_json)

    if plan.proposal_id != proposal.proposal_id:
        raise ValueError(
            "Planner returned a different proposal_id"
        )

    return plan
