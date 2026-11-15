import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.agents.oxylabs_client import (
    OxylabsClient,
    OxylabsAPIError,
)
from app.schemas.verification import (
    ResearchInput,
    ResearchSource,
    ResearchResult,
)


def tokenize(text: str) -> set[str]:
    """Extract normalized terms for deterministic relevance scoring."""
    return {
        word.lower()
        for word in re.findall(r"\b[\w'-]{3,}\b", text)
    }


def score_search_result(
    claim_terms: set[str],
    result: dict,
) -> int:
    """Score a search result based on claim-term overlap."""

    title = str(result.get("title", ""))
    snippet = str(
        result.get("outline")
        or result.get("overview")
        or result.get("snippet")
        or ""
    )

    title_terms = tokenize(title)
    snippet_terms = tokenize(snippet)

    return (
        len(claim_terms & title_terms) * 3
        + len(claim_terms & snippet_terms)
    )


def extract_relevant_passages(
    claim_text: str,
    page_content: str,
    max_characters: int = 12000,
) -> str:
    """
    Select relevant paragraphs from scraped Markdown.

    Original page content is not modified or stored here.
    Only selected passages are returned to the verification pipeline.
    """

    claim_terms = tokenize(claim_text)

    paragraphs = re.split(
        r"\n\s*\n",
        page_content,
    )

    scored_paragraphs = []

    for index, paragraph in enumerate(paragraphs):
        cleaned = re.sub(
            r"!\[[^\]]*\]\([^)]*\)",
            "",
            paragraph,
        )

        cleaned = re.sub(
            r"\[([^\]]+)\]\([^)]*\)",
            r"\1",
            cleaned,
        )

        cleaned = re.sub(r"[#>*`]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) < 80:
            continue

        paragraph_terms = tokenize(cleaned)
        overlap = len(claim_terms & paragraph_terms)

        if overlap == 0:
            continue

        scored_paragraphs.append(
            (overlap, index, cleaned)
        )

    scored_paragraphs.sort(
        key=lambda item: (-item[0], item[1])
    )

    selected = []
    total_characters = 0

    for _, _, paragraph in scored_paragraphs:
        remaining = max_characters - total_characters

        if remaining <= 0:
            break

        if len(paragraph) > remaining:
            paragraph = paragraph[:remaining]

        selected.append(paragraph)
        total_characters += len(paragraph)

    if not selected:
        return page_content[:max_characters].strip()

    return "\n\n".join(selected)


def create_source_id(url: str) -> str:
    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()[:16]

    return f"oxy_{digest}"


def research_claim(
    request: ResearchInput,
    client: OxylabsClient | None = None,
) -> ResearchResult:
    """
    Search and collect external evidence for one factual claim.

    This agent gathers evidence only. It does not determine
    whether the claim is true or false.
    """

    owns_client = client is None

    if owns_client:
        client = OxylabsClient()

    warnings = []
    sources = []

    search_query = (
        request.search_query.strip()
        if request.search_query
        else request.claim_text
    )

    try:
        search_results = client.search(
            query=search_query,
            max_results=request.max_results,
            location=request.location,
        )

        claim_terms = tokenize(request.claim_text)

        ranked_results = []

        for position, item in enumerate(search_results, start=1):
            url = item.get("url")

            if not isinstance(url, str):
                continue

            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                continue

            if not parsed.netloc:
                continue

            ranked_results.append(
                (
                    score_search_result(claim_terms, item),
                    position,
                    item,
                )
            )

        ranked_results.sort(
            key=lambda item: (-item[0], item[1])
        )

        seen_urls = set()
        selected_results = []

        for score, position, item in ranked_results:
            url = item["url"]

            if url in seen_urls:
                continue

            seen_urls.add(url)

            selected_results.append(
                (score, position, item)
            )

            if len(selected_results) >= request.scrape_top_n:
                break

        for score, position, item in selected_results:
            url = item["url"]

            try:
                page = client.scrape(url)

                markdown = page.get("markdown", "")

                if not isinstance(markdown, str) or not markdown.strip():
                    warnings.append(
                        f"No Markdown content returned for {url}"
                    )
                    continue

                content = extract_relevant_passages(
                    request.claim_text,
                    markdown,
                )

                if not content.strip():
                    warnings.append(
                        f"No relevant passages extracted from {url}"
                    )
                    continue

                title = str(
                    item.get("title")
                    or page.get("title")
                    or url
                )

                snippet = (
                    item.get("outline")
                    or item.get("overview")
                    or item.get("snippet")
                )

                source = ResearchSource(
                    source_id=create_source_id(url),
                    title=title,
                    url=url,
                    search_snippet=(
                        str(snippet) if snippet else None
                    ),
                    content=content,
                    search_position=position,
                    source_date=(
                        str(item.get("date"))
                        if item.get("date")
                        else None
                    ),
                    retrieved_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                )

                sources.append(source)

            except OxylabsAPIError as exc:
                warnings.append(
                    f"Could not scrape {url}: {exc}"
                )

        summary = (
            f"Found {len(search_results)} search candidates, "
            f"selected {len(selected_results)}, and successfully "
            f"scraped {len(sources)} sources."
        )

        return ResearchResult(
            proposal_id=request.proposal_id,
            claim_id=request.claim_id,
            search_query=search_query,
            sources=sources,
            candidates_found=len(search_results),
            pages_scraped=len(sources),
            warnings=warnings,
            summary=summary,
        )

    finally:
        if owns_client and client is not None:
            client.close()
