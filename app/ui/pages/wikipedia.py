"""Live demo page: a Wikipedia-styled article view where publishing an edit
triggers WikiGuardian in real time - exactly the "edit -> save -> the guardian
checks past data and real-world sources, and stops false information" flow.

It reuses the real pipeline: proposal_service to record the edit, then
verify_proposal (the full seven-agent run, now temporally aware), showing each
claim's verdict as it arrives and blocking the publish on any contradiction.
"""

import streamlit as st

from app.schemas.verification import PlannerInput
from app.services.article_service import (
    list_articles_with_history,
    get_article_content,
)
from app.services.database_service import get_database_connection
from app.services.proposal_service import create_proposal
from app.services.temporal_service import get_change_signals
from app.services.verification_service import verify_proposal


_WIKI_CSS = """
<style>
    .wiki-wordmark {
        font-family: 'Georgia', 'Linux Libertine', serif;
        font-size: 1.4rem;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .wiki-wordmark .guardian { color: #2e7d32; }
    .wiki-title {
        font-family: 'Georgia', 'Linux Libertine', serif;
        font-size: 2.1rem;
        font-weight: 400;
        border-bottom: 1px solid #a2a9b1;
        padding-bottom: 6px;
        margin-bottom: 4px;
    }
    .wiki-sub {
        color: #54595d;
        font-size: 0.8rem;
        margin-bottom: 14px;
    }
    .wiki-badge {
        display: inline-block;
        background: #eafaf1;
        border: 1px solid #2e7d32;
        color: #1b5e20;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.75rem;
        margin-bottom: 12px;
    }
    .wiki-body {
        font-family: 'Georgia', 'Linux Libertine', serif;
        line-height: 1.6;
    }
    .wg-block {
        background: #fdecea;
        border: 2px solid #c62828;
        border-radius: 8px;
        padding: 16px 18px;
        margin: 8px 0 14px 0;
    }
    .wg-block h3 { color: #b71c1c; margin: 0 0 6px 0; }
    .wg-pass {
        background: #eafaf1;
        border: 2px solid #2e7d32;
        border-radius: 8px;
        padding: 16px 18px;
        margin: 8px 0 14px 0;
    }
    .wg-pass h3 { color: #1b5e20; margin: 0 0 6px 0; }
</style>
"""


def _lead_section(text: str, max_chars: int = 2200) -> str:
    """The article's lead (intro) section - what an editor usually changes, and
    small enough to verify fast. Falls back to a character cap."""

    text = text or ""
    parts = text.split("\n\n")
    lead = parts[0]

    # If the first block is just the heading, include the next paragraph.
    if len(lead) < 200 and len(parts) > 1:
        lead = lead + "\n\n" + parts[1]

    return lead[:max_chars].strip()


def _verdict_badge(verdict: str) -> str:
    colors = {
        "supported": "#2e7d32",
        "contradicted": "#c62828",
        "insufficient_evidence": "#f9a825",
    }
    color = colors.get(verdict, "#54595d")
    label = verdict.replace("_", " ").upper()
    return (
        f"<span style='background:{color};color:white;border-radius:4px;"
        f"padding:1px 7px;font-size:0.75rem;'>{label}</span>"
    )


def _run_guardian(content, edited_text, editor_name, edit_summary):
    """Record the edit and run WikiGuardian live, blocking on contradictions."""

    original_text = content["text"]

    if edited_text.strip() == original_text.strip():
        st.info("No changes detected - edit the text before publishing.")
        return

    try:
        proposal_id = create_proposal(
            article_id=content["article_id"],
            original_text=original_text,
            proposed_text=edited_text,
            edit_summary=edit_summary or "Live demo edit",
            editor_name=editor_name or "Demo editor",
        )
    except Exception as exc:
        st.error(f"Could not record the edit: {exc}")
        return

    planner_input = PlannerInput(
        proposal_id=str(proposal_id),
        article_title=content["title"],
        language_code=content["language_code"],
        edit_summary=edit_summary or "Live demo edit",
        old_text=original_text,
        proposed_text=edited_text,
    )

    connection = None
    result = None

    with st.status(
        "WikiGuardian activated - verifying before publish...", expanded=True
    ) as status:
        try:
            connection = get_database_connection()

            # Stage 1 - the past: system-versioned revision history (instant).
            status.write("Checking past revisions (system-versioned history)...")
            signals = get_change_signals(
                content["wikipedia_page_id"], connection=connection
            )
            if signals:
                verdict_word = (
                    "CONTESTED" if signals["contested"] else "routine"
                )
                status.write(
                    f"History: {signals['total_versions']} versions, "
                    f"{signals['reverts']} reverts - {verdict_word}."
                )

            # Stage 2 - the world: full seven-agent verification.
            status.write(
                "Extracting claims and checking internal knowledge + "
                "real-world sources..."
            )

            def on_progress(record):
                decision = record.decision
                status.write(
                    f"- Claim: \"{record.claim.claim_text[:90]}\" -> "
                    f"{decision.verdict.value} "
                    f"({decision.confidence:.0%} confidence)"
                )

            result = verify_proposal(
                proposal=planner_input,
                connection=connection,
                progress_callback=on_progress,
            )

            status.update(label="WikiGuardian verification complete", state="complete")

        except Exception as exc:
            status.update(label="Verification failed", state="error")
            st.error(f"Verification error: {exc}")
            return
        finally:
            if connection is not None:
                connection.close()

    if result is None:
        return

    contradicted = [
        d for d in result.decisions if d.verdict.value == "contradicted"
    ]

    if contradicted:
        st.markdown(
            "<div class='wg-block'><h3>&#128737; WikiGuardian stopped this edit</h3>"
            "False or unverifiable information was detected. The edit was "
            "<b>not published</b>.</div>",
            unsafe_allow_html=True,
        )
        for decision in contradicted:
            st.markdown(
                f"{_verdict_badge('contradicted')} &nbsp; "
                f"**confidence {decision.confidence:.0%}**",
                unsafe_allow_html=True,
            )
            st.write(decision.reasoning)
    elif result.decisions:
        st.markdown(
            "<div class='wg-pass'><h3>&#9989; No contradictions found</h3>"
            "WikiGuardian found no false claims. The edit is sent to a human "
            "reviewer - WikiGuardian never auto-publishes.</div>",
            unsafe_allow_html=True,
        )
        for decision in result.decisions:
            st.markdown(
                f"{_verdict_badge(decision.verdict.value)} &nbsp; "
                f"**confidence {decision.confidence:.0%}**",
                unsafe_allow_html=True,
            )
            st.caption(decision.reasoning)
    else:
        st.info(
            "No independently verifiable factual claims were found in this edit. "
            "Sent to human review."
        )

    st.caption(
        f"Full audit trail saved (proposal #{proposal_id}) - see the Review "
        "Queue and History pages."
    )


def render_wikipedia():
    st.markdown(_WIKI_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='wiki-wordmark'>Wiki<span class='guardian'>Guardian</span>"
        "pedia</div>",
        unsafe_allow_html=True,
    )
    st.caption("A Wikipedia reading + editing demo, protected by WikiGuardian.")

    try:
        articles = list_articles_with_history()
    except Exception as exc:
        st.error(f"Could not load articles: {exc}")
        return

    if not articles:
        st.warning(
            "No articles with revision history are loaded yet. Import Dataset S "
            "(current text) and Dataset M (history) first."
        )
        return

    titles = {a["title"]: a for a in articles}
    chosen_title = st.selectbox("Article", list(titles.keys()))
    selected = titles[chosen_title]

    try:
        content = get_article_content(selected["article_id"])
    except Exception as exc:
        st.error(f"Could not load article: {exc}")
        return

    if content is None:
        st.warning("This article has no readable content.")
        return

    st.divider()

    st.markdown(
        f"<div class='wiki-title'>{content['title']}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='wiki-sub'>From WikiGuardian-protected Wikipedia (demo). "
        "Finnish Wikipedia, history of Finland.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='wiki-badge'>&#128737; Protected by WikiGuardian</span>",
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "mode",
        ["Read", "Edit"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"wiki_mode_{selected['article_id']}",
    )

    if mode == "Read":
        preview = content["text"]
        if len(preview) > 6000:
            preview = preview[:6000] + "\n\n*(...truncated for display...)*"
        st.markdown(
            f"<div class='wiki-body'>{preview}</div>",
            unsafe_allow_html=True,
        )
        if content["article_url"]:
            st.markdown(f"[View the live article on Wikipedia]({content['article_url']})")
        return

    # Edit mode - edit the lead section only (fast to verify, and where the
    # key facts live).
    lead_text = _lead_section(content["text"])
    edit_content = {**content, "text": lead_text}

    st.caption(
        "You are editing the **lead section**. Try sneaking in a false fact "
        "(for example change a date), then Publish. WikiGuardian checks the "
        "article's own history and real-world sources before anything goes live."
    )

    editor_name = st.text_input(
        "Your editor name",
        value="Anonymous editor",
        key=f"wiki_editor_{selected['article_id']}",
    )
    edit_summary = st.text_input(
        "Edit summary",
        value="",
        placeholder="Briefly describe your change",
        key=f"wiki_summary_{selected['article_id']}",
    )
    edited_text = st.text_area(
        "Lead section",
        value=lead_text,
        height=320,
        key=f"wiki_text_{selected['article_id']}",
    )

    if st.button("Publish changes", type="primary", use_container_width=True):
        _run_guardian(edit_content, edited_text, editor_name, edit_summary)
