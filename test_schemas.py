from app.schemas.verification import (
    Claim,
    VerificationStatus,
    Evidence,
    EvidenceType,
)

claim = Claim(
    claim_id="claim_001",
    claim_text="Helsinki is the capital of Finland.",
    subject="Helsinki",
    predicate="is the capital of",
    object="Finland",
)

print("CLAIM VALIDATION: SUCCESS")
print(claim.model_dump_json(indent=2))

evidence = Evidence(
    evidence_id="evidence_001",
    claim_id="claim_001",
    evidence_type=EvidenceType.EXTERNAL_SOURCE,
    source_title="Example source",
    excerpt="Helsinki is the capital of Finland.",
    supports_claim=True,
)

print("\nEVIDENCE VALIDATION: SUCCESS")
print(evidence.model_dump_json(indent=2))
