from app.services.database_service import get_database_connection


def get_dashboard_metrics():
    """Return aggregate counts for the WikiGuardian dashboard."""

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM articles")
        article_count = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM edit_proposals
            GROUP BY status
            """
        )
        proposal_statuses = {
            status: int(count)
            for status, count in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM verification_runs
            GROUP BY status
            """
        )
        run_statuses = {
            status: int(count)
            for status, count in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT action, COUNT(*)
            FROM review_actions
            GROUP BY action
            """
        )
        review_actions = {
            action: int(count)
            for action, count in cursor.fetchall()
        }

        return {
            "article_count": article_count,
            "proposal_total": sum(proposal_statuses.values()),
            "proposal_statuses": proposal_statuses,
            "run_total": sum(run_statuses.values()),
            "run_statuses": run_statuses,
            "review_total": sum(review_actions.values()),
            "review_actions": review_actions,
        }

    finally:
        cursor.close()
        connection.close()