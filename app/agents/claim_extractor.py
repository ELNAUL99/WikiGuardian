from app.schemas.verification import (
    ClaimExtractionInput,
    ClaimExtractionResult,
)


CLAIM_EXTRACTOR_SYSTEM_PROMPT = """
You are the Claim Extraction Agent of WikiGuardian. You identify independently
verifiable factual claims in a proposed Wikipedia edit. You do NOT judge whether
a claim is true, and you do NOT invent facts.

Return ONLY a valid JSON object with EXACTLY these fields and NO others:

{
  "proposal_id": "<echo the given Proposal ID, as a string>",
  "claims": [
    {
      "claim_id": "c1",
      "claim_text": "a single atomic factual assertion",
      "subject": "the subject of the claim",
      "predicate": "the relationship or property",
      "object": "the value or object",
      "context": "short surrounding context, or an empty string",
      "source_text": "EXACT substring copied verbatim from the Proposed text"
    }
  ],
  "extraction_summary": "one sentence summarising what was extracted"
}

Rules:
1. Break compound sentences into atomic claims; each expresses ONE verifiable
   assertion. Preserve numbers, dates, names and units.
2. Focus on what CHANGED between the Previous text and the Proposed text.
3. "source_text" MUST be copied VERBATIM from the Proposed text (an exact
   substring) - never paraphrased - or the claim is rejected.
4. "subject", "predicate" and "object" are strings; fill them in (use "" only
   if truly not applicable).
5. Every "claim_id" must be unique.
6. If the edit contains no independently verifiable factual claims, return
   "claims": [].
7. "proposal_id" MUST be a string equal to the given Proposal ID.
8. Output ONLY the JSON object - no markdown fences, no commentary, no extra
   fields.
"""


def build_claim_extraction_prompt(
    proposal: ClaimExtractionInput,
) -> str:
    return f"""
Extract atomic factual claims from this Wikipedia edit.

Proposal ID: {proposal.proposal_id}
Article: {proposal.article_title}
Language: {proposal.language_code}

Previous text:
{proposal.old_text}

Proposed text:
{proposal.proposed_text}

Separate independently verifiable claims.
Preserve the original meaning.
Return JSON only.
"""


def parse_claim_extraction_output(
    raw_json: str,
    proposal: ClaimExtractionInput,
) -> ClaimExtractionResult:

    result = ClaimExtractionResult.model_validate_json(raw_json)

    if result.proposal_id != proposal.proposal_id:
        raise ValueError(
            "Claim extractor returned a different proposal_id"
        )

    proposed_text = proposal.proposed_text

    for claim in result.claims:
        if claim.source_text not in proposed_text:
            raise ValueError(
                f"Claim source_text is not present in proposed text: "
                f"{claim.source_text}"
            )

    return result
