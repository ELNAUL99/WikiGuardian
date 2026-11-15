from app.schemas.verification import (
    ResearchInput,
    ResearchSource,
    ResearchResult,
)

request = ResearchInput(
    proposal_id="proposal_001",
    claim_id="claim_001",
    claim_text="Helsinki is the capital of Finland.",
    language_code="en",
    max_results=8,
    scrape_top_n=3,
)

assert request.max_results == 8
assert request.scrape_top_n == 3

source = ResearchSource(
    source_id="oxy_001",
    title="Discover Helsinki",
    url="https://www.visitfinland.com/",
    search_snippet="Helsinki is the capital of Finland.",
    content="Helsinki is the capital and largest city of Finland.",
    search_position=1,
    retrieved_at="2026-11-14T13:00:00Z",
)

result = ResearchResult(
    proposal_id=request.proposal_id,
    claim_id=request.claim_id,
    search_query=request.claim_text,
    sources=[source],
    candidates_found=8,
    pages_scraped=1,
    summary="Retrieved one external source.",
)

print("RESEARCH INPUT VALIDATION: SUCCESS")
print("RESEARCH SOURCE VALIDATION: SUCCESS")
print("RESEARCH RESULT VALIDATION: SUCCESS")
print("Sources:", len(result.sources))
