from app.services.database_service import get_database_connection


def create_proposal(
    article_id: int,
    original_text: str,
    proposed_text: str,
    edit_summary: str,
    editor_name: str | None = None,
) -> int:
    """Persist a proposed article edit and return its proposal ID."""

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    if not isinstance(original_text, str) or not original_text.strip():
        raise ValueError("Original article text cannot be empty.")

    if not isinstance(proposed_text, str) or not proposed_text.strip():
        raise ValueError("Proposed article text cannot be empty.")

    if not isinstance(edit_summary, str) or not edit_summary.strip():
        raise ValueError("An edit summary is required.")

    if len(edit_summary.strip()) > 1000:
        raise ValueError("Edit summary cannot exceed 1000 characters.")

    if original_text.strip() == proposed_text.strip():
        raise ValueError("The proposed text must differ from the original.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO edit_proposals (
                article_id,
                editor_name,
                edit_summary,
                original_text,
                proposed_text,
                status
            )
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                article_id,
                editor_name.strip() if editor_name and editor_name.strip() else None,
                edit_summary.strip(),
                original_text.strip(),
                proposed_text.strip(),
            ),
        )

        proposal_id = cursor.lastrowid
        connection.commit()

        return int(proposal_id)

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_proposal(proposal_id: int):
    """Retrieve one proposal with its associated article metadata."""

    if not isinstance(proposal_id, int) or proposal_id <= 0:
        raise ValueError("A valid proposal ID is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                p.proposal_id,
                p.article_id,
                a.title,
                a.language_code,
                a.article_url,
                p.editor_name,
                p.edit_summary,
                p.original_text,
                p.proposed_text,
                p.status,
                p.submitted_at
            FROM edit_proposals p
            JOIN articles a ON a.article_id = p.article_id
            WHERE p.proposal_id = ?
            """,
            (proposal_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "proposal_id": row[0],
            "article_id": row[1],
            "article_title": row[2],
            "language_code": row[3],
            "article_url": row[4],
            "editor_name": row[5],
            "edit_summary": row[6],
            "original_text": row[7],
            "proposed_text": row[8],
            "status": row[9],
            "submitted_at": row[10],
        }

    finally:
        cursor.close()
        connection.close()

def list_proposals(status: str | None = None, limit: int = 50, offset: int = 0):
    """List proposals with article metadata, newest first."""

    allowed_statuses = {
        "pending",
        "running",
        "completed",
        "failed",
        "approved",
        "rejected",
    }

    if status is not None and status not in allowed_statuses:
        raise ValueError("Unsupported proposal status.")

    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    if not isinstance(offset, int) or offset < 0:
        raise ValueError("Offset cannot be negative.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        query = """
            SELECT
                p.proposal_id,
                p.article_id,
                a.title,
                a.language_code,
                p.editor_name,
                p.edit_summary,
                p.status,
                p.submitted_at
            FROM edit_proposals p
            JOIN articles a ON a.article_id = p.article_id
        """

        parameters = []

        if status is not None:
            query += " WHERE p.status = ?"
            parameters.append(status)

        query += " ORDER BY p.submitted_at DESC, p.proposal_id DESC"
        query += " LIMIT ? OFFSET ?"
        parameters.extend([limit, offset])

        cursor.execute(query, tuple(parameters))
        rows = cursor.fetchall()

        return [
            {
                "proposal_id": row[0],
                "article_id": row[1],
                "article_title": row[2],
                "language_code": row[3],
                "editor_name": row[4],
                "edit_summary": row[5],
                "status": row[6],
                "submitted_at": row[7],
            }
            for row in rows
        ]

    finally:
        cursor.close()
        connection.close()
