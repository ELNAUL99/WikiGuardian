
import argparse
import getpass
import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path

import mariadb
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "mariadb-wikipedia-datasets" / "data" / "s"

LANGUAGES = ["en", "fi", "sv"]
BATCH_SIZE = 100
VECTOR_DIMENSIONS = 1024


def parse_timestamp(value):
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def import_language(cursor, connection, language, limit=None):
    article_file = DATA_DIR / f"articles-{language}.parquet"
    vector_file = DATA_DIR / f"vectors-bge-m3-{language}.parquet"

    if not article_file.exists() or not vector_file.exists():
        raise FileNotFoundError(
            f"Missing dataset files for language: {language}"
        )

    print(f"\nReading {language.upper()} dataset...")

    articles = pq.read_table(article_file).to_pylist()
    vectors = pq.read_table(vector_file).to_pylist()

    vector_map = {
        row["page_id"]: row
        for row in vectors
    }

    if len(articles) != len(vectors):
        raise ValueError(
            f"{language}: article/vector counts do not match"
        )

    if limit is not None:
        articles = articles[:limit]

    imported = 0

    for article in articles:
        page_id = article["page_id"]
        vector_row = vector_map.get(page_id)

        if vector_row is None:
            raise ValueError(f"Missing embedding for page {page_id}")

        if vector_row["lang"] != language:
            raise ValueError(f"Language mismatch for page {page_id}")

        text = article["text"] or ""
        embedding = vector_row["embedding"]

        if len(embedding) != VECTOR_DIMENSIONS:
            raise ValueError(
                f"Page {page_id}: expected {VECTOR_DIMENSIONS} "
                f"dimensions, received {len(embedding)}"
            )

        revision_timestamp = parse_timestamp(article["date_modified"])
        digest = content_hash(text)

        # 1. Insert or update the article.
        cursor.execute(
            """
            INSERT INTO articles
                (wikipedia_page_id, language_code, title, article_url)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                article_id = LAST_INSERT_ID(article_id),
                title = VALUES(title),
                article_url = VALUES(article_url)
            """,
            (
                page_id,
                language,
                article["title"],
                article["url"],
            ),
        )

        article_id = cursor.lastrowid

        if not article_id:
            raise RuntimeError(f"Could not resolve article {page_id}")

        # 2. Store the original Wikipedia revision.
        cursor.execute(
            """
            INSERT INTO article_revisions
                (
                    article_id,
                    wikipedia_revision_id,
                    wikipedia_timestamp,
                    article_content,
                    content_hash
                )
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                revision_id = LAST_INSERT_ID(revision_id),
                wikipedia_timestamp = VALUES(wikipedia_timestamp),
                article_content = VALUES(article_content),
                content_hash = VALUES(content_hash)
            """,
            (
                article_id,
                article["rev_id"],
                revision_timestamp,
                text,
                digest,
            ),
        )

        # 3. Store one full-article chunk.
        cursor.execute(
            """
            INSERT INTO article_chunks
                (
                    article_id,
                    wikipedia_revision_id,
                    chunk_index,
                    section_title,
                    chunk_text,
                    content_hash
                )
            VALUES (?, ?, 0, NULL, ?, ?)
            ON DUPLICATE KEY UPDATE
                chunk_id = LAST_INSERT_ID(chunk_id),
                chunk_text = VALUES(chunk_text),
                content_hash = VALUES(content_hash)
            """,
            (
                article_id,
                article["rev_id"],
                text,
                digest,
            ),
        )

        chunk_id = cursor.lastrowid

        if not chunk_id:
            raise RuntimeError(f"Could not resolve chunk for page {page_id}")

        # 4. Store the precomputed 1024-dimensional vector.
        vector_bytes = struct.pack(
            f"<{VECTOR_DIMENSIONS}f",
            *embedding,
        )

        cursor.execute(
            """
            INSERT INTO chunk_embeddings
                (
                    chunk_id,
                    embedding,
                    embedding_model,
                    embedding_truncated
                )
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                embedding = VALUES(embedding),
                embedding_model = VALUES(embedding_model),
                embedding_truncated = VALUES(embedding_truncated)
            """,
            (
                chunk_id,
                vector_bytes,
                vector_row["model"],
                int(vector_row["truncated"]),
            ),
        )

        imported += 1

        # Commit periodically. If interrupted, rerunning is safe.
        if imported % BATCH_SIZE == 0:
            connection.commit()
            print(f"  Processed {imported} articles...")

    connection.commit()

    print(f"  Finished {language.upper()}: {imported} articles")

    return imported


def main():
    parser = argparse.ArgumentParser(
        description="Import MariaDB Wikipedia Dataset S into WikiGuardian."
    )

    parser.add_argument(
        "--language",
        choices=LANGUAGES,
        help="Import only one language. Default: all three.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of articles per language.",
    )

    args = parser.parse_args()

    languages = [args.language] if args.language else LANGUAGES

    password = getpass.getpass("MariaDB root password: ")

    connection = mariadb.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=password,
        database="wikiguardian",
    )

    cursor = connection.cursor()

    total = 0

    try:
        for language in languages:
            total += import_language(
                cursor,
                connection,
                language,
                args.limit,
            )

        print(f"\nImport complete. Total processed: {total}")

    except Exception:
        connection.rollback()
        print("\nImport failed. The current transaction was rolled back.")
        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
