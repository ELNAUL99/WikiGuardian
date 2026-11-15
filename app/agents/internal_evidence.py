import hashlib

from app.schemas.verification import (
    EvidenceType,
    KnowledgeMatch,
    ResearchSource,
)


def create_internal_source_id(match: KnowledgeMatch) -> str:
    """Create a deterministic ID for a Wikipedia evidence chunk."""

    identity = (
        f"{match.article_id}:"
        f"{match.wikipedia_revision_id}:"
        f"{match.chunk_id}"
    )

    digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16]

    return f"wiki_{digest}"


def knowledge_match_to_source(
    match: KnowledgeMatch,
) -> ResearchSource:
    """Convert a MariaDB knowledge match into unified evidence."""

    if not match.article_url:
        raise ValueError(
            f"Missing article URL for Wikipedia article: {match.title}"
        )

    if not match.chunk_text.strip():
        raise ValueError(
            f"Empty evidence content for Wikipedia article: {match.title}"
        )

    return ResearchSource(
        source_id=create_internal_source_id(match),
        title=match.title,
        url=match.article_url,
        evidence_type=EvidenceType.INTERNAL_WIKIPEDIA,
        search_snippet=None,
        content=match.chunk_text,
        search_position=None,
        source_date=match.wikipedia_timestamp,
        retrieved_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        article_id=match.article_id,
        chunk_id=match.chunk_id,
        language_code=match.language_code,
        wikipedia_revision_id=match.wikipedia_revision_id,
        wikipedia_timestamp=match.wikipedia_timestamp,
        cosine_distance=match.cosine_distance,
    )


def convert_knowledge_matches(
    matches: list[KnowledgeMatch],
) -> list[ResearchSource]:
    """Convert retrieved matches while preserving their ranking."""

    sources = [
        knowledge_match_to_source(match)
        for match in matches
    ]

    source_ids = [source.source_id for source in sources]

    if len(source_ids) != len(set(source_ids)):
        raise ValueError(
            "Duplicate internal Wikipedia evidence source IDs."
        )

    return sources
