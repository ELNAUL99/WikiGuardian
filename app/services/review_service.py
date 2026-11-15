from app.services.article_state_service import record_human_decision
from app.services.database_service import get_database_connection


def submit_review(
    proposal_id: int,
    reviewer_name: str,
    action: str,
    reviewer_comment: str,
) -> int:
    """Record a human decision and update proposal status atomically."""

    if not isinstance(proposal_id, int) or proposal_id <= 0:
        raise ValueError("Proposal ID must be a positive integer.")

    reviewer_name = reviewer_name.strip() if reviewer_name else ""
    reviewer_comment = (
        reviewer_comment.strip() if reviewer_comment else ""
    )

    if not reviewer_name:
        raise ValueError("Reviewer name is required.")

    if action not in {"approved", "rejected"}:
        raise ValueError("Action must be approved or rejected.")

    if not reviewer_comment:
        raise ValueError("A reviewer comment is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT status, article_id
            FROM edit_proposals
            WHERE proposal_id = ?
            FOR UPDATE
            """,
            (proposal_id,),
        )

        row = cursor.fetchone()

        if row is None:
            raise ValueError("Proposal does not exist.")

        current_status = row[0]
        article_id = int(row[1])

        if current_status in {"approved", "rejected"}:
            raise ValueError(
                "This proposal has already received a final human decision."
            )

        if current_status not in {"pending", "completed", "failed"}:
            raise ValueError(
                f"Proposal cannot be reviewed in status: {current_status}"
            )

        cursor.execute(
            """
            INSERT INTO review_actions (
                proposal_id,
                reviewer_name,
                action,
                reviewer_comment
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                proposal_id,
                reviewer_name,
                action,
                reviewer_comment,
            ),
        )

        review_id = int(cursor.lastrowid)

        cursor.execute(
            """
            UPDATE edit_proposals
            SET status = ?
            WHERE proposal_id = ?
            """,
            (action, proposal_id),
        )

        # Move WikiGuardian's own editorial state in the same transaction,
        # so the human decision and the system-versioned state transition
        # commit atomically together.
        record_human_decision(
            connection,
            article_id,
            action,
            proposal_id=proposal_id,
            reviewer_name=reviewer_name,
            reviewer_comment=reviewer_comment,
        )

        connection.commit()
        return review_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def get_review_history(proposal_id: int):
    """Retrieve the chronological human-review audit trail."""

    if not isinstance(proposal_id, int) or proposal_id <= 0:
        raise ValueError("Proposal ID must be a positive integer.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                review_id,
                reviewer_name,
                action,
                reviewer_comment,
                reviewed_at
            FROM review_actions
            WHERE proposal_id = ?
            ORDER BY reviewed_at DESC, review_id DESC
            """,
            (proposal_id,),
        )

        return [
            {
                "review_id": row[0],
                "reviewer_name": row[1],
                "action": row[2],
                "reviewer_comment": row[3],
                "reviewed_at": row[4],
            }
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()