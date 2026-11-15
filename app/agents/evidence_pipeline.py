from app.schemas.verification import (
    EvidenceType,
    ResearchSource,
)


def combine_evidence_sources(
    internal_sources: list[ResearchSource],
    external_sources: list[ResearchSource],
) -> list[ResearchSource]:
    """Combine internal and external evidence without losing provenance."""

    for source in internal_sources:
        if source.evidence_type != EvidenceType.INTERNAL_WIKIPEDIA:
            raise ValueError(
                f"Expected internal Wikipedia source: {source.source_id}"
            )

    for source in external_sources:
        if source.evidence_type != EvidenceType.EXTERNAL_SOURCE:
            raise ValueError(
                f"Expected external source: {source.source_id}"
            )

    combined = [*internal_sources, *external_sources]

    source_ids = [source.source_id for source in combined]

    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Duplicate evidence source IDs.")

    return combined
