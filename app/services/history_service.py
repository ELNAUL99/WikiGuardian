from app.services.database_service import get_database_connection


def list_verification_runs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Retrieve verification runs with proposal and article metadata."""

    allowed_statuses = {"pending", "running", "completed", "failed"}

    if status is not None and status not in allowed_statuses:
        raise ValueError("Unsupported verification run status.")

    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    if not isinstance(offset, int) or offset < 0:
        raise ValueError("Offset cannot be negative.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        query = """
            SELECT
                vr.run_id,
                vr.proposal_id,
                a.title,
                a.language_code,
                vr.status,
                vr.llm_model,
                vr.embedding_model,
                vr.started_at,
                vr.completed_at,
                vr.error_message
            FROM verification_runs vr
            JOIN edit_proposals ep
                ON ep.proposal_id = vr.proposal_id
            JOIN articles a
                ON a.article_id = ep.article_id
        """

        parameters = []

        if status is not None:
            query += " WHERE vr.status = ?"
            parameters.append(status)

        query += " ORDER BY vr.started_at DESC, vr.run_id DESC"
        query += " LIMIT ? OFFSET ?"
        parameters.extend([limit, offset])

        cursor.execute(query, tuple(parameters))
        rows = cursor.fetchall()

        return [
            {
                "run_id": row[0],
                "proposal_id": row[1],
                "article_title": row[2],
                "language_code": row[3],
                "status": row[4],
                "llm_model": row[5],
                "embedding_model": row[6],
                "started_at": row[7],
                "completed_at": row[8],
                "error_message": row[9],
            }
            for row in rows
        ]

    finally:
        cursor.close()
        connection.close()

def get_verification_run_details(run_id: int):
    """Retrieve a verification run and its complete claim audit trail."""

    if not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("Run ID must be a positive integer.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                vr.run_id,
                vr.proposal_id,
                vr.llm_model,
                vr.embedding_model,
                vr.status,
                vr.started_at,
                vr.completed_at,
                vr.error_message,
                a.title,
                a.language_code,
                ep.edit_summary
            FROM verification_runs vr
            JOIN edit_proposals ep
                ON ep.proposal_id = vr.proposal_id
            JOIN articles a
                ON a.article_id = ep.article_id
            WHERE vr.run_id = ?
            """,
            (run_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        run = {
            "run_id": row[0],
            "proposal_id": row[1],
            "llm_model": row[2],
            "embedding_model": row[3],
            "status": row[4],
            "started_at": row[5],
            "completed_at": row[6],
            "error_message": row[7],
            "article_title": row[8],
            "language_code": row[9],
            "edit_summary": row[10],
        }

        cursor.execute(
            """
            SELECT
                c.claim_id,
                c.claim_text,
                vd.verdict,
                vd.confidence,
                vd.explanation,
                vd.verification_history,
                vd.recommendation,
                vd.requires_human_review,
                vd.decided_at
            FROM verification_decisions vd
            JOIN claims c
                ON c.claim_id = vd.claim_id
            WHERE vd.run_id = ?
            ORDER BY c.claim_id
            """,
            (run_id,),
        )

        claim_rows = cursor.fetchall()

        claims = []

        for claim_row in claim_rows:
            claim_id = claim_row[0]

            cursor.execute(
                """
                SELECT
                    es.evidence_id,
                    es.source_title,
                    es.source_url,
                    es.publisher,
                    es.published_at,
                    es.retrieved_at,
                    es.source_type,
                    ce.evidence_relation,
                    ce.relevant_excerpt,
                    ce.relevance_score,
                    ce.explanation
                FROM claim_evidence ce
                JOIN evidence_sources es
                    ON es.evidence_id = ce.evidence_id
                WHERE ce.claim_id = ?
                ORDER BY ce.relevance_score DESC
                """,
                (claim_id,),
            )

            evidence = [
                {
                    "evidence_id": item[0],
                    "source_title": item[1],
                    "source_url": item[2],
                    "publisher": item[3],
                    "published_at": item[4],
                    "retrieved_at": item[5],
                    "source_type": item[6],
                    "evidence_relation": item[7],
                    "relevant_excerpt": item[8],
                    "relevance_score": item[9],
                    "explanation": item[10],
                }
                for item in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    objection_id,
                    round_number,
                    issue_type,
                    severity,
                    objection,
                    source_ids,
                    requires_reassessment
                FROM critique_findings
                WHERE run_id = ? AND claim_id = ?
                ORDER BY round_number, finding_id
                """,
                (run_id, claim_id),
            )

            critiques = [
                {
                    "objection_id": item[0],
                    "round_number": item[1],
                    "issue_type": item[2],
                    "severity": item[3],
                    "objection": item[4],
                    "source_ids": item[5],
                    "requires_reassessment": item[6],
                }
                for item in cursor.fetchall()
            ]

            claims.append(
                {
                    "claim_id": claim_id,
                    "claim_text": claim_row[1],
                    "verdict": claim_row[2],
                    "confidence": claim_row[3],
                    "explanation": claim_row[4],
                    "verification_history": claim_row[5],
                    "recommendation": claim_row[6],
                    "requires_human_review": claim_row[7],
                    "decided_at": claim_row[8],
                    "evidence": evidence,
                    "critiques": critiques,
                }
            )

        return {
            "run": run,
            "claims": claims,
        }

    finally:
        cursor.close()
        connection.close()