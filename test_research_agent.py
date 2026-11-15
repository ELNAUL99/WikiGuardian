from app.agents.research_agent import research_claim
from app.schemas.verification import ResearchInput


request = ResearchInput(
    proposal_id="proposal_test_001",
    claim_id="claim_test_001",
    claim_text="Helsinki is the capital of Finland.",
    language_code="en",
    max_results=5,
    scrape_top_n=2,
)

result = research_claim(request)

print("\nRESEARCH AGENT TEST: SUCCESS")
print("Proposal:", result.proposal_id)
print("Claim:", result.claim_id)
print("Candidates found:", result.candidates_found)
print("Pages scraped:", result.pages_scraped)
print("Summary:", result.summary)

for source in result.sources:
    print("\n------------------------------")
    print("Source ID:", source.source_id)
    print("Title:", source.title)
    print("URL:", source.url)
    print("Search position:", source.search_position)
    print("Content length:", len(source.content))
    print("Content preview:")
    print(source.content[:500])

if result.warnings:
    print("\nWarnings:")
    for warning in result.warnings:
        print("-", warning)

if not result.sources:
    raise RuntimeError(
        "Research Agent returned no usable sources."
    )

print("\nRESEARCH AGENT INTEGRATION: SUCCESS")
