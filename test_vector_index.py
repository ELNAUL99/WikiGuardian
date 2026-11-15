import getpass
import mariadb

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

    if row is None:
        raise RuntimeError("Asgard embedding not found.")

    embedding = bytes(row[0])

    cursor.execute(
        """
        EXPLAIN
        SELECT
            chunk_id,
            VEC_DISTANCE_COSINE(embedding, ?) AS distance
        FROM chunk_embeddings
        ORDER BY VEC_DISTANCE_COSINE(embedding, ?)
        LIMIT ?
        """,
        (embedding, embedding, 5),
    )

    print("\nVECTOR INDEX QUERY PLAN:")
    for result in cursor.fetchall():
        print(result)

    cursor.close()

finally:
    connection.close()
