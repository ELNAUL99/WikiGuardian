from app.services.database_service import get_database_connection


SUPPORTED_LANGUAGES = ("en", "fi", "sv")


def search_articles(language_code: str, query: str = "", limit: int = 30):
    """Search imported Wikipedia articles by language and title."""

    if language_code not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported article language.")

    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Article search limit must be between 1 and 100.")

    normalized_query = query.strip()

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        if normalized_query:
            cursor.execute(
                """
                SELECT article_id, wikipedia_page_id, title,
                       language_code, article_url
                FROM articles
                WHERE language_code = ?
                  AND title LIKE ?
                ORDER BY title
                LIMIT ?
                """,
                (
                    language_code,
                    f"%{normalized_query}%",
                    limit,
                ),
            )
        else:
            cursor.execute(
                """
                SELECT article_id, wikipedia_page_id, title,
                       language_code, article_url
                FROM articles
                WHERE language_code = ?
                ORDER BY title
                LIMIT ?
                """,
                (language_code, limit),
            )

        rows = cursor.fetchall()

        return [
            {
                "article_id": row[0],
                "wikipedia_page_id": row[1],
                "title": row[2],
                "language_code": row[3],
                "article_url": row[4],
            }
            for row in rows
        ]

    finally:
        cursor.close()
        connection.close()


def list_articles_with_history(limit: int = 100):
    """List articles that have Wikipedia revision history loaded (for the live
    demo): Finnish articles present in both `articles` and `article_history`."""

    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT DISTINCT a.article_id, a.title, a.wikipedia_page_id
            FROM articles a
            JOIN article_history h ON h.page_id = a.wikipedia_page_id
            WHERE a.language_code = 'fi'
            ORDER BY a.title
            LIMIT ?
            """,
            (limit,),
        )

        return [
            {
                "article_id": row[0],
                "title": row[1],
                "wikipedia_page_id": row[2],
            }
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()


def get_article_content(article_id: int):
    """Return an article's current text and metadata for the Wikipedia view."""

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT a.title, a.article_url, a.language_code,
                   a.wikipedia_page_id, c.chunk_text
            FROM articles a
            LEFT JOIN article_chunks c
                ON c.article_id = a.article_id AND c.chunk_index = 0
            WHERE a.article_id = ?
            """,
            (article_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "article_id": article_id,
            "title": row[0],
            "article_url": row[1],
            "language_code": row[2],
            "wikipedia_page_id": row[3],
            "text": row[4] or "",
        }

    finally:
        cursor.close()
        connection.close()