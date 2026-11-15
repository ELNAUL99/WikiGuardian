"""WikiGuardian's own editorial state per article, backed by a MariaDB
System-Versioned Table (SVT).

Every change to a row in `guardian_article_state` is archived automatically by MariaDB,
so the full history of what WikiGuardian believed about an article is queryable
with FOR SYSTEM_TIME. This is deliberately separate from Wikipedia's own
revision chronology (article_revisions.wikipedia_timestamp).

Write transitions wired into the app:
    * AI verification completes -> 'under_review'  (advisory; no human yet)
    * human approves            -> 'verified'
    * human rejects             -> 'disputed'

Human-in-the-loop principle: the AI never sets 'verified'. Only a human review
promotes an article to 'verified'.
"""

from app.services.database_service import get_database_connection


VALID_STATUSES = {
    "unverified",
    "under_review",
    "verified",
    "disputed",
}

# MariaDB stores the current row's end bound as the maximum TIMESTAMP value.
# Any row_end in this year or later marks the still-current version.
_CURRENT_ROW_END_YEAR = 2038


def _lookup_article_id(cursor, proposal_id: int):
    """Resolve the article a proposal belongs to, using the caller's cursor."""

    cursor.execute(
        """
        SELECT article_id
        FROM edit_proposals
        WHERE proposal_id = ?
        """,
        (proposal_id,),
    )

    row = cursor.fetchone()

    if row is None:
        raise ValueError(f"Proposal {proposal_id} does not exist.")

    return int(row[0])


def set_article_state(
    connection,
    article_id: int,
    guardian_status: str,
    *,
    current_revision_id: int | None = None,
    last_proposal_id: int | None = None,
    last_run_id: int | None = None,
    confidence: float | None = None,
    note: str | None = None,
    updated_by: str = "system",
):
    """Upsert the current editorial state for an article.

    The caller owns the connection and its transaction: this function never
    commits. On MariaDB the UPDATE path automatically archives the previous
    row as system-versioned history.

    This writes a full state snapshot, so values left as None replace whatever
    was stored before.
    """

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    if guardian_status not in VALID_STATUSES:
        raise ValueError(f"Unsupported guardian status: {guardian_status}")

    note = note[:1000] if note else None
    updated_by = (updated_by or "system")[:255]

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO guardian_article_state (
                article_id,
                guardian_status,
                current_revision_id,
                last_proposal_id,
                last_run_id,
                confidence,
                note,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                guardian_status = VALUES(guardian_status),
                current_revision_id = VALUES(current_revision_id),
                last_proposal_id = VALUES(last_proposal_id),
                last_run_id = VALUES(last_run_id),
                confidence = VALUES(confidence),
                note = VALUES(note),
                updated_by = VALUES(updated_by)
            """,
            (
                article_id,
                guardian_status,
                current_revision_id,
                last_proposal_id,
                last_run_id,
                confidence,
                note,
                updated_by,
            ),
        )

    finally:
        cursor.close()


def record_ai_review(connection, proposal_id: int, run_id: int, result):
    """Move an article to 'under_review' after AI verification completes.

    Best-effort and part of the caller's transaction: the caller commits.
    `result` is a VerificationResult.
    """

    cursor = connection.cursor()

    try:
        article_id = _lookup_article_id(cursor, int(proposal_id))
    finally:
        cursor.close()

    confidences = [
        decision.confidence
        for decision in result.decisions
        if decision.confidence is not None
    ]

    average_confidence = (
        sum(confidences) / len(confidences) if confidences else None
    )

    set_article_state(
        connection,
        article_id,
        "under_review",
        last_proposal_id=int(proposal_id),
        last_run_id=int(run_id),
        confidence=average_confidence,
        note=result.overall_summary,
        updated_by="system",
    )


def record_human_decision(
    connection,
    article_id: int,
    action: str,
    *,
    proposal_id: int | None = None,
    reviewer_name: str | None = None,
    reviewer_comment: str | None = None,
):
    """Apply a human approve/reject to the article's editorial state.

    Part of the caller's transaction: the caller commits.
    """

    guardian_status = "verified" if action == "approved" else "disputed"

    set_article_state(
        connection,
        article_id,
        guardian_status,
        last_proposal_id=proposal_id,
        note=reviewer_comment,
        updated_by=reviewer_name or "reviewer",
    )


def _row_is_current(row_end) -> bool:
    """Whether a history row is the still-current version."""

    year = getattr(row_end, "year", None)
    return year is not None and year >= _CURRENT_ROW_END_YEAR


def get_current_state(article_id: int):
    """Return the article's current editorial state, or None."""

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                guardian_status,
                confidence,
                note,
                updated_by,
                last_run_id,
                last_proposal_id,
                current_revision_id
            FROM guardian_article_state
            WHERE article_id = ?
            """,
            (article_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "article_id": article_id,
            "guardian_status": row[0],
            "confidence": row[1],
            "note": row[2],
            "updated_by": row[3],
            "last_run_id": row[4],
            "last_proposal_id": row[5],
            "current_revision_id": row[6],
        }

    finally:
        cursor.close()
        connection.close()


def get_state_history(article_id: int):
    """Return every version of the article's state, oldest first.

    Uses FOR SYSTEM_TIME ALL to read the system-versioned history, including
    the invisible row_start / row_end period columns.
    """

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                guardian_status,
                confidence,
                note,
                updated_by,
                last_run_id,
                last_proposal_id,
                current_revision_id,
                row_start,
                row_end
            FROM guardian_article_state
            FOR SYSTEM_TIME ALL
            WHERE article_id = ?
            ORDER BY row_start
            """,
            (article_id,),
        )

        return [
            {
                "guardian_status": row[0],
                "confidence": row[1],
                "note": row[2],
                "updated_by": row[3],
                "last_run_id": row[4],
                "last_proposal_id": row[5],
                "current_revision_id": row[6],
                "valid_from": row[7],
                "valid_to": row[8],
                "is_current": _row_is_current(row[8]),
            }
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()
