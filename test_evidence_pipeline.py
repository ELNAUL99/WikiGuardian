import getpass
import struct

import mariadb

from app.schemas.verification import (
    EvidenceType,
    KnowledgeRetrievalInput,
    ResearchSource,
)
from app.agents.knowledge_retriever import retrieve_knowledge
from app.agents.internal_evidence import convert_knowledge_matches
from app.agents.evidence_pipeline import combine_evidence_sources


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

    embedding = list(
        struct.unpack("<1024f", embedding_bytes)
    )

    request = KnowledgeRetrievalInput(
        claim_id="test_claim_pipeline",
        claim_text="Test combined evidence pipeline.",
        embedding=embedding,
        top_k=5,
        language_code="en",
    )

    retrieval = retrieve_knowledge(connection, request)
    internal_sources = convert_knowledge_matches(retrieval.matches)

    external_source = ResearchSource(
        source_id="oxy_test_external_001",
        title="Example external reference",
        url="https://example.com/reference",
        evidence_type=EvidenceType.EXTERNAL_SOURCE,
        search_snippet="Example search snippet",
        content="Example external evidence content.",
        retrieved_at="2026-11-14T14:00:00+00:00",
    )

    combined = combine_evidence_sources(
        internal_sources=internal_sources,
        external_sources=[external_source],
    )

    internal_count = sum(
        source.evidence_type == EvidenceType.INTERNAL_WIKIPEDIA
        for source in combined
    )

    external_count = sum(
        source.evidence_type == EvidenceType.EXTERNAL_SOURCE
        for source in combined
    )

    if internal_count != len(internal_sources):
        raise RuntimeError("Internal evidence count mismatch.")

    if external_count != 1:
        raise RuntimeError("External evidence count mismatch.")

    if len(combined) != len(internal_sources) + 1:
        raise RuntimeError("Combined evidence count mismatch.")

    print("\nEVIDENCE PIPELINE TEST: SUCCESS")
    print("Internal sources:", internal_count)
    print("External sources:", external_count)
    print("Combined sources:", len(combined))
    print("First source:", combined[0].title)
    print("Last source:", combined[-1].title)

    # Duplicate source IDs must be rejected.
    try:
        combine_evidence_sources(
            internal_sources=internal_sources,
            external_sources=[internal_sources[0]],
        )
    except ValueError:
        print("Duplicate source rejection: SUCCESS")
    else:
        raise RuntimeError("Duplicate source ID was not rejected.")

    # Incorrect evidence classification must be rejected.
    try:
        combine_evidence_sources(
            internal_sources=[external_source],
            external_sources=[],
        )
    except ValueError:
        print("Evidence type validation: SUCCESS")
    else:
        raise RuntimeError("Incorrect evidence type was not rejected.")

finally:
    connection.close()
