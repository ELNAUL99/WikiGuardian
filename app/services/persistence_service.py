import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.schemas.persistence import (
    ClaimExecutionRecord,
    VerificationRunMetadata,
)


class VerificationPersistence:
    """Persist verification results and their audit history in MariaDB."""

    def __init__(self, connection, metadata: VerificationRunMetadata):
        self.connection = connection
        self.metadata = metadata
        self.run_id = None
        self.claim_id_map = {}
        self.evidence_id_map = {}

        try:
            self.proposal_id = int(metadata.proposal_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("proposal_id must be a positive integer.") from exc

        if self.proposal_id <= 0:
            raise ValueError("proposal_id must be a positive integer.")

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )

            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

            return parsed
        except (TypeError, ValueError):
            return None

    def start_run(self):
        if self.run_id is not None:
            raise RuntimeError("Verification run already started.")

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                """
                SELECT status
                FROM edit_proposals
                WHERE proposal_id = ?
                FOR UPDATE
                """,
                (self.proposal_id,),
            )

            proposal_row = cursor.fetchone()

            if proposal_row is None:
                raise ValueError(
                    f"Proposal {self.proposal_id} does not exist."
                )

            proposal_status = proposal_row[0]

            if proposal_status == "running":
                raise RuntimeError(
                    "This proposal is already being verified."
                )

            if proposal_status in {"approved", "rejected"}:
                raise RuntimeError(
                    "A finalized proposal cannot be verified again."
                )

            if proposal_status not in {"pending", "completed", "failed"}:
                raise RuntimeError(
                    f"Unsupported proposal status: {proposal_status}"
                )

            cursor.execute(
                """
                UPDATE edit_proposals
                SET status = 'running'
                WHERE proposal_id = ?
                """,
                (self.proposal_id,),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Could not mark the proposal as running."
                )

            cursor.execute(
                """
                INSERT INTO verification_runs (
                    proposal_id,
                    llm_model,
                    embedding_model,
                    status
                )
                VALUES (?, ?, ?, 'running')
                """,
                (
                    self.proposal_id,
                    self.metadata.llm_model,
                    self.metadata.embedding_model,
                ),
            )

            self.run_id = cursor.lastrowid
            self.connection.commit()
            return self.run_id

        except Exception:
            self.connection.rollback()
            self.run_id = None
            raise

        finally:
            cursor.close()

    def _get_or_create_evidence(self, cursor, source):
        source_url = str(source.url)
        source_type = source.evidence_type.value
        content_hash = hashlib.sha256(
            source.content.encode("utf-8")
        ).hexdigest()

        provenance = None

        if source_type == "internal_wikipedia":
            provenance = self._json({
                "article_id": source.article_id,
                "chunk_id": source.chunk_id,
                "language_code": source.language_code,
                "wikipedia_revision_id": source.wikipedia_revision_id,
                "wikipedia_timestamp": source.wikipedia_timestamp,
                "cosine_distance": source.cosine_distance,
            })

        evidence_id = None

        if source_type == "external_source":
            cursor.execute(
                """
                SELECT evidence_id
                FROM evidence_sources
                WHERE source_url = ?
                  AND content_hash = ?
                  AND source_type = ?
                ORDER BY evidence_id
                LIMIT 1
                """,
                (source_url, content_hash, source_type),
            )

            existing = cursor.fetchone()

            if existing:
                evidence_id = existing[0]

        if evidence_id is None:
            publisher = urlparse(source_url).hostname

            cursor.execute(
                """
                INSERT INTO evidence_sources (
                    source_url,
                    source_title,
                    publisher,
                    published_at,
                    source_content,
                    content_hash,
                    source_type,
                    provenance
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_url,
                    source.title[:1000],
                    publisher[:500] if publisher else None,
                    self._parse_datetime(source.source_date),
                    source.content,
                    content_hash,
                    source_type,
                    provenance,
                ),
            )

            evidence_id = cursor.lastrowid

        return evidence_id

    def save_claim_execution(self, record: ClaimExecutionRecord):
        if self.run_id is None:
            raise RuntimeError("Start the verification run first.")

        cursor = self.connection.cursor()

        try:
            claim = record.claim

            cursor.execute(
                """
                INSERT INTO claims (
                    proposal_id,
                    claim_text,
                    subject,
                    predicate,
                    object_value
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.proposal_id,
                    claim.claim_text,
                    claim.subject,
                    claim.predicate,
                    claim.object,
                ),
            )

            database_claim_id = cursor.lastrowid
            self.claim_id_map[claim.claim_id] = database_claim_id

            # Keep source IDs scoped to this claim to avoid cross-claim collisions.
            source_database_ids = {}

            for source in record.sources:
                source_database_ids[source.source_id] = (
                    self._get_or_create_evidence(cursor, source)
                )

                self.evidence_id_map[
                    f"{claim.claim_id}:{source.source_id}"
                ] = source_database_ids[source.source_id]

            # Store evidence relationships from the final verification round.
            if record.verification_rounds:
                latest_verification = record.verification_rounds[-1]

                for assessment in latest_verification.source_assessments:
                    evidence_id = source_database_ids.get(
                        assessment.source_id
                    )

                    if evidence_id is None:
                        raise ValueError(
                            "Verification references an unknown source: "
                            f"{assessment.source_id}"
                        )

                    cursor.execute(
                        """
                        INSERT INTO claim_evidence (
                            claim_id,
                            evidence_id,
                            evidence_relation,
                            relevant_excerpt,
                            relevance_score,
                            explanation
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON DUPLICATE KEY UPDATE
                            evidence_relation = VALUES(evidence_relation),
                            relevant_excerpt = VALUES(relevant_excerpt),
                            relevance_score = VALUES(relevance_score),
                            explanation = VALUES(explanation)
                        """,
                        (
                            database_claim_id,
                            evidence_id,
                            assessment.position.value,
                            assessment.quoted_excerpt,
                            assessment.relevance,
                            assessment.reasoning,
                        ),
                    )

            # Persist critique findings from every challenge round.
            for critique in record.critique_rounds:
                for finding in critique.findings:
                    mapped_source_ids = []

                    for source_id in finding.source_ids:
                        if source_id not in source_database_ids:
                            raise ValueError(
                                "Critique references an unknown source: "
                                f"{source_id}"
                            )

                        mapped_source_ids.append(
                            source_database_ids[source_id]
                        )

                    stored_objection_id = (
                        f"r{critique.round_number}:{finding.objection_id}"
                    )

                    cursor.execute(
                        """
                        INSERT INTO critique_findings (
                            run_id,
                            claim_id,
                            objection_id,
                            round_number,
                            issue_type,
                            severity,
                            objection,
                            source_ids,
                            requires_reassessment
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.run_id,
                            database_claim_id,
                            stored_objection_id,
                            critique.round_number,
                            finding.issue_type.value,
                            finding.severity.value,
                            finding.objection,
                            self._json(mapped_source_ids),
                            finding.requires_reassessment,
                        ),
                    )

            decision = record.decision

            for source_id in (
                decision.supporting_source_ids
                + decision.contradicting_source_ids
            ):
                if source_id not in source_database_ids:
                    raise ValueError(
                        "Decision references an unknown source: "
                        f"{source_id}"
                    )

            recommendation = {
                "summary": decision.summary,
                "supporting_source_ids": [
                    source_database_ids[item]
                    for item in decision.supporting_source_ids
                ],
                "contradicting_source_ids": [
                    source_database_ids[item]
                    for item in decision.contradicting_source_ids
                ],
                "considered_objection_ids": [
                    f"r{critique.round_number}:{finding.objection_id}"
                    for critique in record.critique_rounds
                    for finding in critique.findings
                    if finding.objection_id in decision.considered_objection_ids
                ],
                "original_considered_objection_ids": (
                    decision.considered_objection_ids
                ),
                "requires_reassessment": decision.requires_reassessment,
            }

            verification_history = [
                item.model_dump(mode="json")
                for item in record.verification_rounds
            ]

            cursor.execute(
                """
                INSERT INTO verification_decisions (
                    run_id,
                    claim_id,
                    verdict,
                    confidence,
                    explanation,
                    verification_history,
                    recommendation,
                    requires_human_review
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    database_claim_id,
                    decision.verdict.value,
                    decision.confidence,
                    decision.reasoning,
                    self._json(verification_history),
                    self._json(recommendation),
                    True,
                ),
            )

            self.connection.commit()
            return database_claim_id

        except Exception:
            self.connection.rollback()
            raise

        finally:
            cursor.close()

    def complete_run(self):
        self._update_run_status("completed")

    def fail_run(self, error):
        self._update_run_status("failed", str(error))

    def _update_run_status(self, status, error_message=None):
        if self.run_id is None:
            raise RuntimeError("No verification run has been started.")

        if status not in {"completed", "failed"}:
            raise ValueError("Invalid final verification status.")

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                """
                UPDATE verification_runs
                SET status = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE run_id = ?
                  AND status = 'running'
                """,
                (status, error_message, self.run_id),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Could not finalize the verification run."
                )

            cursor.execute(
                """
                UPDATE edit_proposals
                SET status = ?
                WHERE proposal_id = ?
                  AND status = 'running'
                """,
                (status, self.proposal_id),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Could not finalize the proposal status."
                )

            self.connection.commit()

        except Exception:
            self.connection.rollback()
            raise

        finally:
            cursor.close()
