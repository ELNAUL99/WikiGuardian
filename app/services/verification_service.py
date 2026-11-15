from app.agents.oxylabs_client import OxylabsClient
from app.orchestrator.verification_orchestrator import run_verification
from app.providers.llm_provider import get_llm_client
from app.schemas.persistence import VerificationRunMetadata
from app.schemas.verification import PlannerInput
from app.services import temporal_service
from app.services.article_state_service import record_ai_review
from app.services.embedding_service import EmbeddingService
from app.services.persistence_service import VerificationPersistence


def _build_temporal_context(connection, proposal) -> str:
    """Summarize the edited article's Wikipedia revision history for the agents.

    Best-effort and read-only, reusing the caller's connection so it adds no new
    database connection. Returns "" when the article has no loaded history, so
    verification is unaffected for articles outside Dataset M.
    """

    try:
        proposal_id = int(proposal.proposal_id)
    except (TypeError, ValueError):
        return ""

    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT article_id FROM edit_proposals WHERE proposal_id = ?",
                (proposal_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()

        if not row:
            return ""

        page_id = temporal_service.resolve_page_id(int(row[0]), connection=connection)
        if not page_id:
            return ""

        signals = temporal_service.get_change_signals(page_id, connection=connection)
        if not signals:
            return ""
    except Exception:
        return ""

    lines = [
        "Background about the Wikipedia article being edited, from its full",
        "revision history. This is NOT evidence for or against any claim; weigh",
        "it when calibrating confidence and how strongly to require human review.",
        "",
        f"- Article: {signals['title']} (page {signals['page_id']})",
        (
            f"- History: {signals['total_versions']} versions from "
            f"{signals['first_edit']} to {signals['last_edit']}, by "
            f"{signals['distinct_editors']} editors ({signals['anonymous_edits']} anonymous)."
        ),
        (
            f"- Reverts: {signals['reverts']}; busiest single day: "
            f"{signals['busiest_day_edits']} edits."
        ),
    ]

    if signals["contested"]:
        lines.append(
            "- ASSESSMENT: CONTESTED topic (edit-war signals) - scrutinize closely."
        )
    else:
        lines.append("- ASSESSMENT: edit activity looks routine.")

    return "\n".join(lines)


def verify_proposal(
    proposal: PlannerInput,
    connection,
    top_k: int = 5,
    progress_callback=None,
    on_stage=None,
):
    """Run verification and persist its complete audit trail.

    The caller owns the MariaDB connection. `progress_callback`, if given, is
    called with each ClaimExecutionRecord as that claim finishes, so a live UI
    can show verdicts arriving in real time.
    """

    llm_client = get_llm_client()
    embedding_service = EmbeddingService()
    oxylabs_client = OxylabsClient()

    persistence = VerificationPersistence(
        connection=connection,
        metadata=VerificationRunMetadata(
            proposal_id=str(proposal.proposal_id),
            llm_model=llm_client.model,
            embedding_model=embedding_service.model,
        ),
    )

    persistence.start_run()

    def _on_claim(record):
        persistence.save_claim_execution(record)
        if progress_callback is not None:
            try:
                progress_callback(record)
            except Exception:
                # Progress reporting must never break verification.
                pass

    try:
        if on_stage is not None:
            on_stage("Checking past revisions (system-versioned history)...")

        temporal_context = _build_temporal_context(connection, proposal)

        result = run_verification(
            proposal=proposal,
            connection=connection,
            model_call=llm_client,
            embed_text=embedding_service,
            oxylabs_client=oxylabs_client,
            top_k=top_k,
            on_claim_completed=_on_claim,
            temporal_context=temporal_context,
            on_stage=on_stage,
        )

        persistence.complete_run()

        # Record WikiGuardian's own editorial state (system-versioned).
        # Best-effort: the run is already committed, so a state-write
        # failure must not turn a completed verification into a failure.
        try:
            record_ai_review(
                connection,
                proposal_id=int(proposal.proposal_id),
                run_id=persistence.run_id,
                result=result,
            )
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass

        return result

    except Exception as exc:
        try:
            persistence.fail_run(exc)
        except Exception:
            # Preserve the original verification exception.
            pass

        raise
