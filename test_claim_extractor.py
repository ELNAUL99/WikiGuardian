from app.schemas.verification import ClaimExtractionInput
from app.agents.claim_extractor import (
    CLAIM_EXTRACTOR_SYSTEM_PROMPT,
    build_claim_extraction_prompt,
    parse_claim_extraction_output,
)

proposal = ClaimExtractionInput(
    proposal_id="proposal_002",
    article_title="Helsinki",
    language_code="en",
    old_text="Helsinki is the capital of Finland.",
    proposed_text=(
        "Helsinki is the capital of Finland and has "
        "approximately 700000 residents."
    ),
)

mock_response = """
{
    "proposal_id": "proposal_002",
    "claims": [
        {
            "claim_id": "claim_001",
            "claim_text": "Helsinki is the capital of Finland.",
            "subject": "Helsinki",
            "predicate": "is the capital of",
            "object": "Finland",
            "context": "Political status",
            "source_text": "Helsinki is the capital of Finland"
        },
        {
            "claim_id": "claim_002",
            "claim_text": "Helsinki has approximately 700000 residents.",
            "subject": "Helsinki",
            "predicate": "has a population of",
            "object": "approximately 700000 residents",
            "context": "Population",
            "source_text": "has approximately 700000 residents"
        }
    ],
    "extraction_summary": "Two independently verifiable factual claims identified."
}
"""

prompt = build_claim_extraction_prompt(proposal)

result = parse_claim_extraction_output(
    mock_response,
    proposal
)

print("CLAIM EXTRACTOR TEST: SUCCESS")
print("System prompt available:", bool(CLAIM_EXTRACTOR_SYSTEM_PROMPT))
print("User prompt generated:", bool(prompt))
print("Claims extracted:", len(result.claims))
print(result.model_dump_json(indent=2))
