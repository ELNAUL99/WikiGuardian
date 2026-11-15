"""FastAPI backend for the WikiGuardian "Wikipedia clone" demo.

Serves a MediaWiki-Vector-skin frontend and exposes:
    GET  /api/articles        - articles that have revision history loaded
    GET  /api/article/{id}    - one article's content (+ editable lead)
    POST /api/verify          - run WikiGuardian live, STREAMING progress (SSE)

The verify endpoint runs the real seven-agent pipeline in a background thread and
streams each stage as it happens (planning, claim extraction, past-revision
check, evidence, verification, critique, decision), then the final verdict. A
contradicted claim means the edit is blocked.

Run:  uvicorn app.api.server:app --port 8600
"""

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas.verification import PlannerInput
from app.services.article_service import (
    get_article_content,
    list_articles_with_history,
)
from app.services.database_service import get_database_connection
from app.services.proposal_service import create_proposal
from app.services.temporal_service import get_change_signals
from app.services.verification_service import verify_proposal


ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "app" / "web"

app = FastAPI(title="WikiGuardian - Wikipedia demo")


def _lead_section(text: str, max_chars: int = 2200) -> str:
    parts = (text or "").split("\n\n")
    lead = parts[0]
    if len(lead) < 200 and len(parts) > 1:
        lead = lead + "\n\n" + parts[1]
    return lead[:max_chars].strip()


@app.get("/api/articles")
def api_articles():
    return list_articles_with_history()


@app.get("/api/article/{article_id}")
def api_article(article_id: int):
    content = get_article_content(article_id)
    if not content:
        return JSONResponse({"error": "not found"}, status_code=404)
    content = dict(content)
    content["lead"] = _lead_section(content["text"])
    return content


@app.post("/api/verify")
async def api_verify(request: Request):
    body = await request.json()
    article_id = int(body["article_id"])
    proposed = body.get("proposed_text", "") or ""
    editor = (body.get("editor_name") or "Anonymous editor").strip()
    summary = (body.get("edit_summary") or "Edit via WikiGuardianpedia").strip()

    events: "queue.Queue[dict]" = queue.Queue()

    def emit(event: dict):
        events.put(event)

    def run():
        connection = None
        try:
            content = get_article_content(article_id)
            if not content:
                emit({"type": "error", "message": "Article not found."})
                return

            original = _lead_section(content["text"])
            if proposed.strip() == original.strip():
                emit({"type": "error", "message": "No changes detected - edit the lead before saving."})
                return

            proposal_id = create_proposal(
                article_id=article_id,
                original_text=original,
                proposed_text=proposed,
                edit_summary=summary,
                editor_name=editor,
            )
            emit({"type": "proposal", "proposal_id": proposal_id})

            connection = get_database_connection()

            try:
                signals = get_change_signals(
                    content["wikipedia_page_id"], connection=connection
                )
            except Exception:
                signals = None

            if signals:
                emit({
                    "type": "signal",
                    "title": signals["title"],
                    "versions": signals["total_versions"],
                    "reverts": signals["reverts"],
                    "contested": signals["contested"],
                })

            planner_input = PlannerInput(
                proposal_id=str(proposal_id),
                article_title=content["title"],
                language_code=content["language_code"],
                edit_summary=summary,
                old_text=original,
                proposed_text=proposed,
            )

            def on_stage(message):
                emit({"type": "stage", "message": message})

            def on_claim(record):
                decision = record.decision
                emit({
                    "type": "claim",
                    "claim": record.claim.claim_text,
                    "verdict": decision.verdict.value,
                    "confidence": decision.confidence,
                })

            result = verify_proposal(
                proposal=planner_input,
                connection=connection,
                progress_callback=on_claim,
                on_stage=on_stage,
            )

            contradicted = [
                d for d in result.decisions if d.verdict.value == "contradicted"
            ]

            emit({
                "type": "result",
                "blocked": bool(contradicted),
                "summary": result.overall_summary,
                "proposal_id": proposal_id,
                "decisions": [
                    {
                        "verdict": d.verdict.value,
                        "confidence": d.confidence,
                        "reasoning": d.reasoning,
                    }
                    for d in result.decisions
                ],
            })

        except Exception as exc:
            emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            if connection is not None:
                connection.close()
            emit({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            event = events.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Serve the static Wikipedia-skin frontend (registered last so /api/* win).
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
