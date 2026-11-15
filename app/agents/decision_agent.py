import json
from typing import Any

from app.schemas.verification import (
    DecisionAgentInput,
    DecisionAgentResult,
    CritiqueSeverity,
)


DECISION_SYSTEM_PROMPT = """
You are the Confidence and Decision Agent in WikiGuardian.

Your responsibility is to synthesize the Verification Agent's assessment and
the Critique Agent's findings into a carefully calibrated claim decision.

Rules:
1. Evaluate the exact claim, not a broader or narrower interpretation.
2. Consider every verification source assessment and every critique finding.
3. Distinguish source quantity from source independence. Multiple sources
   repeating the same underlying information are not independent corroboration.
4. Consider source reliability, relevance, dates, context, and limitations.
5. Treat internal Wikipedia retrieval as contextual evidence, not automatic proof.
6. Do not invent sources, source IDs, objection IDs, quotations, or facts.
7. Use only source IDs and objection IDs supplied in the input.
8. A supported verdict requires credible evidence supporting the claim.
9. A contradicted verdict requires credible evidence contradicting the claim.
10. Use insufficient_evidence when the evidence is inconclusive, unreliable,
    materially incomplete, or evenly conflicting.
11. Calibrate confidence conservatively. Do not equate confidence with the
    Verification Agent's confidence.
12. If a high or critical critique finding requires reassessment, explicitly
    flag requires_reassessment.
13. If the Critique Agent disagrees with the original verdict, address that
    disagreement explicitly. Do not silently ignore it.
14. Do not approve, reject, publish, or modify a Wikipedia article.
15. Human review is always required.

Return only valid JSON matching this structure:
{
  "claim_id": "string",
  "verdict": "supported | contradicted | insufficient_evidence",
  "confidence": 0.0,
  "supporting_source_ids": [],
  "contradicting_source_ids": [],
  "considered_objection_ids": [],
  "reasoning": "Detailed evidence-based reasoning",
  "summary": "Concise decision summary",
  "requires_reassessment": false,
  "requires_human_review": true
}
"""


def build_decision_prompt(request: DecisionAgentInput) -> str:
    payload = request.model_dump(mode="json")

    return (
        "Evaluate this claim and produce the final decision.\n\n"
        "INPUT:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def parse_decision_output(
    raw_json: str,
    request: DecisionAgentInput,
) -> DecisionAgentResult:
    try:
        data: Any = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Decision Agent returned invalid JSON: {exc}") from exc

    result = DecisionAgentResult.model_validate(data)

    if result.claim_id != request.claim_id:
        raise ValueError("Decision claim_id does not match input claim_id.")

    # Defence in depth: the final decision cannot establish
    # a factual verdict when no evidence sources were available.
    if (
        not request.sources
        and result.verdict.value != "insufficient_evidence"
    ):
        raise ValueError(
            "Decision Agent cannot return a supported or contradicted "
            "verdict without evidence sources."
        )

    available_source_ids = {
        source.source_id for source in request.sources
    }

    cited_source_ids = (
        result.supporting_source_ids
        + result.contradicting_source_ids
    )

    if len(cited_source_ids) != len(set(cited_source_ids)):
        raise ValueError("A source ID cannot appear more than once in the decision.")

    unknown_sources = set(cited_source_ids) - available_source_ids
    if unknown_sources:
        raise ValueError(
            f"Decision references unknown source IDs: {sorted(unknown_sources)}"
        )

    objection_ids = {
        finding.objection_id
        for finding in request.critique.findings
    }

    if len(result.considered_objection_ids) != len(
        set(result.considered_objection_ids)
    ):
        raise ValueError("Duplicate objection IDs in decision.")

    unknown_objections = set(result.considered_objection_ids) - objection_ids
    if unknown_objections:
        raise ValueError(
            f"Decision references unknown objection IDs: "
            f"{sorted(unknown_objections)}"
        )

    if result.verdict == request.verification.verdict:
        pass
    elif (
        request.critique.alternative_verdict is not None
        and result.verdict != request.critique.alternative_verdict
        and not result.requires_reassessment
    ):
        raise ValueError(
            "Decision contradicts both the original and alternative verdict "
            "without flagging reassessment."
        )

    serious_findings = [
        finding
        for finding in request.critique.findings
        if finding.requires_reassessment
        and finding.severity in {
            CritiqueSeverity.HIGH,
            CritiqueSeverity.CRITICAL,
        }
    ]

    if serious_findings and not result.requires_reassessment:
        raise ValueError(
            "High or critical critique findings require reassessment."
        )

    if not result.requires_human_review:
        raise ValueError("Human review cannot be disabled.")

    # Enforce conservative confidence calibration when material concerns exist.
    if serious_findings and result.confidence > 0.60:
        raise ValueError(
            "Confidence exceeds 0.60 despite high/critical findings requiring "
            "reassessment."
        )

    if (
        not request.critique.agrees_with_verdict
        and result.confidence > 0.75
    ):
        raise ValueError(
            "Confidence exceeds 0.75 despite disagreement from the Critique Agent."
        )

    return result
