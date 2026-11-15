import getpass
import struct

import mariadb

from app.schemas.verification import KnowledgeRetrievalInput
from app.agents.knowledge_retriever import retrieve_knowledge


connection = mariadb.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password=getpass.getpass("MariaDB password: "),
    database="wikiguardian",
)

try:
    cursor = connection.cursor()

    # Reuse an existing Dataset S embedding.
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
        raise RuntimeError(
            "Could not find the Asgard embedding."
        )

    embedding_bytes = bytes(row[0])

    if len(embedding_bytes) != 4096:
        raise RuntimeError(
            f"Expected 4096 embedding bytes, got "
            f"{len(embedding_bytes)}"
        )

    embedding = list(
        struct.unpack("<1024f", embedding_bytes)
    )

    request = KnowledgeRetrievalInput(
        claim_id="test_claim_001",
        claim_text="Test retrieval using the Asgard article embedding.",
        embedding=embedding,
        top_k=5,
        language_code="en",
    )

    result = retrieve_knowledge(connection, request)

    print("\nKNOWLEDGE RETRIEVER TEST: SUCCESS")
    print("Candidates examined:", result.candidates_examined)
    print("Matches returned:", len(result.matches))
    print("\nRetrieved articles:")

    for match in result.matches:
        print(
            f"\nTitle: {match.title}"
            f"\nLanguage: {match.language_code}"
            f"\nRevision: {match.wikipedia_revision_id}"
            f"\nCosine distance: {match.cosine_distance:.8f}"
            f"\nChunk length: {len(match.chunk_text)} characters"
        )

    if not result.matches:
        raise RuntimeError("No knowledge matches were returned.")

    if result.matches[0].title != "Asgard":
        raise RuntimeError(
            "Expected Asgard to be the closest match."
        )

    if result.matches[0].cosine_distance > 0.001:
        raise RuntimeError(
            "Asgard's self-match distance is unexpectedly high."
        )

finally:
    connection.close()
