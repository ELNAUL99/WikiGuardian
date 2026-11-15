import struct

from app.schemas.verification import (
    KnowledgeRetrievalInput,
    KnowledgeRetrievalResult,
    KnowledgeMatch,
)


EMBEDDING_DIMENSION = 1024


def retrieve_knowledge(
    connection,
    request: KnowledgeRetrievalInput,
) -> KnowledgeRetrievalResult:
    """
    Retrieve semantically similar article chunks from MariaDB.

    The connection is supplied by the caller so database credentials
    and connection lifecycle remain outside the agent.
    """

    if len(request.embedding) != EMBEDDING_DIMENSION:
        raise ValueError("Expected a 1024-dimensional embedding")

    query_vector = struct.pack(
        "<1024f",
        *request.embedding
    )

    # Retrieve extra candidates when language filtering is requested.
    candidate_limit = (
        min(request.top_k * 5, 100)
        if request.language_code
        else request.top_k
    )

    cursor = connection.cursor()

    try:
        # Stage 1: Vector similarity search.
        # The ORDER BY expression and LIMIT allow MariaDB to use
        # the matching cosine vector index.
        cursor.execute(
            """
            SELECT
                chunk_id,
                VEC_DISTANCE_COSINE(embedding, ?) AS distance
            FROM chunk_embeddings
            ORDER BY VEC_DISTANCE_COSINE(embedding, ?)
            LIMIT ?
            """,
            (
                query_vector,
                query_vector,
                candidate_limit,
            ),
        )

        ranked_rows = cursor.fetchall()

        if not ranked_rows:
            return KnowledgeRetrievalResult(
                claim_id=request.claim_id,
                matches=[],
                candidates_examined=0,
                summary="No matching knowledge chunks found.",
            )

        distances = {
            int(row[0]): float(row[1])
            for row in ranked_rows
        }

        chunk_ids = list(distances.keys())
        placeholders = ", ".join("?" for _ in chunk_ids)

        # Stage 2: Fetch article text and revision metadata.
        cursor.execute(
            f"""
            SELECT
                c.chunk_id,
                c.article_id,
                a.title,
                a.language_code,
                a.article_url,
                c.wikipedia_revision_id,
                r.wikipedia_timestamp,
                c.chunk_index,
                c.section_title,
                c.chunk_text
            FROM article_chunks AS c
            JOIN articles AS a
                ON a.article_id = c.article_id
            LEFT JOIN article_revisions AS r
                ON r.article_id = c.article_id
                AND r.wikipedia_revision_id = c.wikipedia_revision_id
            WHERE c.chunk_id IN ({placeholders})
            """,
            tuple(chunk_ids),
        )

        metadata_rows = cursor.fetchall()

        metadata_by_id = {
            int(row[0]): row
            for row in metadata_rows
        }

        matches = []

        # Preserve vector-search ranking.
        for chunk_id in chunk_ids:
            row = metadata_by_id.get(chunk_id)

            if row is None:
                continue

            if (
                request.language_code
                and row[3] != request.language_code
            ):
                continue

            timestamp = row[6]

            matches.append(
                KnowledgeMatch(
                    chunk_id=int(row[0]),
                    article_id=int(row[1]),
                    title=row[2],
                    language_code=row[3],
                    article_url=row[4],
                    wikipedia_revision_id=row[5],
                    wikipedia_timestamp=(
                        timestamp.isoformat(sep=" ")
                        if timestamp is not None
                        else None
                    ),
                    chunk_index=int(row[7]),
                    section_title=row[8],
                    chunk_text=row[9],
                    cosine_distance=distances[chunk_id],
                )
            )

            if len(matches) >= request.top_k:
                break

        return KnowledgeRetrievalResult(
            claim_id=request.claim_id,
            matches=matches,
            candidates_examined=len(ranked_rows),
            summary=(
                f"Retrieved {len(matches)} knowledge matches "
                f"from {len(ranked_rows)} vector candidates."
            ),
        )

    finally:
        cursor.close()
