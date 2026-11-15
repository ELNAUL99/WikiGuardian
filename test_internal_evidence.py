import getpass
import struct

import mariadb

from app.schemas.verification import (
    EvidenceType,
    KnowledgeRetrievalInput,
)
from app.agents.knowledge_retriever import retrieve_knowledge
from app.agents.internal_evidence import (
    convert_knowledge_matches,
)


connection = mariadb.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password=getpass.getpass("MariaDB password: "),
    database="wikiguardian",
)

try:
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT e.embedding
        FROM chunk_embeddings AS e
        JOIN article_chunks AS c
            ON c.chunk_id = e.chunk_id
        JOIN articles AS a
            ON a.article_id = c.article_id
        WHERE a.title = ?
          AND a.language_code = ?
        LIMIT 1
        """,
        ("Asgard", "en"),
    )

    row = cursor.fetchone()
    cursor.close()

    if row is None:
        raise RuntimeError("Could not find Asgard embedding.")

    embedding_bytes = bytes(row[0])

    if len(embedding_bytes) != 4096:
        raise RuntimeError("Unexpected embedding size.")

    embedding = list(
        struct.unpack("<1024f", embedding_bytes)
    )

    request = KnowledgeRetrievalInput(
        claim_id="test_claim_internal",
        claim_text="Test internal Wikipedia evidence conversion.",
        embedding=embedding,
        top_k=5,
        language_code="en",
    )

    retrieval = retrieve_knowledge(connection, request)

    if not retrieval.matches:
        raise RuntimeError("No knowledge matches returned.")

    sources = convert_knowledge_matches(retrieval.matches)

    if len(sources) != len(retrieval.matches):
        raise RuntimeError("Evidence conversion lost matches.")

    for match, source in zip(retrieval.matches, sources):
        if source.evidence_type != EvidenceType.INTERNAL_WIKIPEDIA:
            raise RuntimeError("Incorrect evidence type.")

        if source.article_id != match.article_id:
            raise RuntimeError("Article ID mismatch.")

        if source.chunk_id != match.chunk_id:
            raise RuntimeError("Chunk ID mismatch.")

        if source.wikipedia_revision_id != match.wikipedia_revision_id:
            raise RuntimeError("Revision ID mismatch.")

        if source.cosine_distance != match.cosine_distance:
            raise RuntimeError("Cosine distance mismatch.")

        if source.content != match.chunk_text:
            raise RuntimeError("Evidence content mismatch.")

    print("\nINTERNAL EVIDENCE ADAPTER TEST: SUCCESS")
    print("Matches converted:", len(sources))
    print("Evidence type:", sources[0].evidence_type.value)
    print("First article:", sources[0].title)
    print("First source ID:", sources[0].source_id)
    print("Revision:", sources[0].wikipedia_revision_id)
    print("Cosine distance:", sources[0].cosine_distance)

finally:
    connection.close()
