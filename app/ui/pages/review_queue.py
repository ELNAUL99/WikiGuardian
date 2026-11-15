from datetime import date, datetime, time

import streamlit as st

from app.services.verification_service import verify_proposal
from app.schemas.verification import PlannerInput
from app.services.database_service import get_database_connection
from app.services.proposal_service import get_proposal, list_proposals
from app.services.review_service import get_review_history, submit_review
from app.services.article_state_service import (
    get_current_state,
    get_state_history,
)
from app.services.temporal_service import (
    resolve_page_id,
    get_change_signals,
    get_content_as_of,
    get_revision_timeline,
)


def render_review_queue():
    st.title("Human Review Queue")
    st.write(
        "Inspect submitted Wikipedia edits and their current verification status."
    )

    status_filter = st.selectbox(
        "Filter by status",
        options=[
            "All",
            "pending",
            "running",
            "completed",
            "failed",
            "approved",
            "rejected",
        ],
    )

    if st.button("Refresh queue"):
        st.session_state.pop("review_queue_selection", None)
        st.rerun()

    try:
        proposals = list_proposals(
            status=None if status_filter == "All" else status_filter,
            limit=50,
        )
    except Exception as exc:
        st.error(f"Could not load proposals: {exc}")
        return

    if not proposals:
        st.info("No proposals match this filter.")
        return

    st.caption(f"{len(proposals)} proposal(s) displayed")

    for item in proposals:
        submitted_at = item["submitted_at"]
        submitted_label = (
            submitted_at.strftime("%Y-%m-%d %H:%M")
            if submitted_at
            else "Unknown"
        )

        with st.container(border=True):
            left, right = st.columns([4, 1])

            with left:
                st.subheader(item["article_title"])
                st.caption(
                    f"Proposal #{item['proposal_id']} | "
                    f"{item['language_code'].upper()} | "
                    f"Submitted {submitted_label}"
                )
                st.write(item["edit_summary"] or "No edit summary")
                st.caption(
                    f"Editor: {item['editor_name'] or 'Not provided'}"
                )

            with right:
                st.markdown(f"**{item['status'].upper()}**")

                if st.button(
                    "Inspect",
                    key=f"inspect_{item['proposal_id']}",
                    use_container_width=True,
                ):
                    st.session_state["review_queue_selection"] = (
                        item["proposal_id"]
                    )

    selected_id = st.session_state.get("review_queue_selection")

    if not selected_id:
        return

    st.divider()
    st.subheader(f"Proposal #{selected_id}")

    try:
        proposal = get_proposal(selected_id)
    except Exception as exc:
        st.error(f"Could not load proposal details: {exc}")
        return

    if proposal is None:
        st.warning("This proposal no longer exists.")
        return

    st.write(f"**Article:** {proposal['article_title']}")
    st.write(f"**Edit summary:** {proposal['edit_summary'] or 'None'}")
    st.write(f"**Status:** {proposal['status']}")

    if proposal["article_url"]:
        st.markdown(
            f"[Open Wikipedia article]({proposal['article_url']})"
        )

    st.markdown("**Original text**")
    st.text_area(
        "Original",
        value=proposal["original_text"] or "",
        height=160,
        disabled=True,
        label_visibility="collapsed",
    )

    st.markdown("**Proposed text**")
    st.text_area(
        "Proposed",
        value=proposal["proposed_text"],
        height=200,
        disabled=True,
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("Article state (system-versioned)")
    st.caption(
        "WikiGuardian's own editorial view of this article. Every change is "
        "preserved automatically by MariaDB system versioning."
    )

    try:
        current_state = get_current_state(int(proposal["article_id"]))
        state_history = get_state_history(int(proposal["article_id"]))
    except Exception as exc:
        st.error(f"Could not load article state: {exc}")
        current_state = None
        state_history = []

    if current_state is None:
        st.caption(
            "No editorial state recorded yet. It is set when AI verification "
            "completes or a human decision is made."
        )
    else:
        confidence = current_state["confidence"]
        confidence_label = (
            f"{confidence:.0%}"
            if isinstance(confidence, (int, float))
            else "n/a"
        )

        state_col, confidence_col = st.columns(2)

        with state_col:
            st.metric(
                "Guardian status",
                current_state["guardian_status"].replace("_", " "),
            )

        with confidence_col:
            st.metric("Avg. AI confidence", confidence_label)

        if current_state["note"]:
            st.caption(current_state["note"])

        with st.expander(
            f"State history ({len(state_history)} version(s))"
        ):
            if not state_history:
                st.caption("No history rows.")

            # Newest first for display; the query returns oldest first.
            for version in reversed(state_history):
                valid_from = version["valid_from"]
                from_label = (
                    valid_from.strftime("%Y-%m-%d %H:%M:%S")
                    if valid_from
                    else "Unknown"
                )

                if version["is_current"]:
                    window = f"{from_label} -> current"
                    badge = "CURRENT"
                else:
                    valid_to = version["valid_to"]
                    to_label = (
                        valid_to.strftime("%Y-%m-%d %H:%M:%S")
                        if valid_to
                        else "Unknown"
                    )
                    window = f"{from_label} -> {to_label}"
                    badge = "past"

                with st.container(border=True):
                    st.markdown(
                        f"**{version['guardian_status'].replace('_', ' ').upper()}**"
                        f" | {badge}"
                    )
                    st.caption(
                        f"{window} | by {version['updated_by'] or 'system'}"
                    )
                    if version["note"]:
                        st.write(version["note"])

    st.divider()
    st.subheader("Wikipedia through time (revision history)")
    st.caption(
        "The article's own Wikipedia edit history, in a MariaDB system-versioned "
        "table. Travel back to any date and see how contested the topic is."
    )

    th_connection = None
    th_page_id = None
    th_signals = None

    try:
        th_connection = get_database_connection()
        th_page_id = resolve_page_id(
            int(proposal["article_id"]), connection=th_connection
        )
        if th_page_id:
            th_signals = get_change_signals(th_page_id, connection=th_connection)
    except Exception as exc:
        st.error(f"Could not load revision history: {exc}")

    try:
        if not th_page_id or not th_signals:
            st.caption(
                "No Wikipedia revision history is loaded for this article "
                "(only a subset of Finnish articles is imported)."
            )
        else:
            metric_cols = st.columns(4)
            metric_cols[0].metric("Versions", th_signals["total_versions"])
            metric_cols[1].metric("Editors", th_signals["distinct_editors"])
            metric_cols[2].metric("Reverts", th_signals["reverts"])
            metric_cols[3].metric(
                "Status", "Contested" if th_signals["contested"] else "Routine"
            )

            if th_signals["contested"]:
                st.warning(
                    f"Contested topic: {th_signals['reverts']} reverts, busiest "
                    f"day {th_signals['busiest_day_edits']} edits. WikiGuardian "
                    "flags this for closer review."
                )

            first_edit = th_signals["first_edit"]
            last_edit = th_signals["last_edit"]
            min_date = (
                first_edit.date() if hasattr(first_edit, "date") else date(2002, 1, 1)
            )
            max_date = (
                last_edit.date() if hasattr(last_edit, "date") else date.today()
            )

            chosen_date = st.date_input(
                "Show the article as it was on:",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key=f"asof_date_{selected_id}",
            )

            snapshot = None
            try:
                as_of_dt = datetime.combine(chosen_date, time(23, 59, 59))
                snapshot = get_content_as_of(
                    th_page_id, as_of_dt, connection=th_connection
                )
            except Exception as exc:
                st.error(f"Point-in-time query failed: {exc}")

            if snapshot is None:
                st.info("The article did not exist yet on that date.")
            else:
                st.caption(
                    f"Revision {snapshot['rev_id']} | {snapshot['bytes']} bytes | "
                    f"editor {snapshot['editor'] or 'unknown'}"
                )
                st.markdown(
                    "[View this exact revision on Wikipedia]"
                    f"(https://fi.wikipedia.org/?oldid={snapshot['rev_id']})"
                )
                st.text_area(
                    "Article wikitext as of this date",
                    value=(snapshot["text"] or "")[:1500],
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"asof_text_{selected_id}",
                )

            with st.expander("Revision timeline (most recent 20)"):
                timeline = []
                try:
                    timeline = get_revision_timeline(
                        th_page_id, connection=th_connection
                    )
                except Exception as exc:
                    st.error(f"Could not load timeline: {exc}")

                if not timeline:
                    st.caption("No revisions found.")

                for version in list(reversed(timeline))[:20]:
                    valid_from = version["valid_from"]
                    when_label = (
                        valid_from.strftime("%Y-%m-%d %H:%M")
                        if valid_from
                        else "Unknown"
                    )
                    flags = []
                    if version["minor"]:
                        flags.append("minor")
                    if version["anonymous"]:
                        flags.append("anon")
                    suffix = f" [{', '.join(flags)}]" if flags else ""
                    st.markdown(
                        f"**{when_label}** | {version['bytes']} bytes | "
                        f"{version['editor'] or 'unknown'}{suffix}"
                    )
                    if version["comment"]:
                        st.caption(version["comment"])
    finally:
        if th_connection is not None:
            th_connection.close()

    st.divider()
    st.subheader("AI factual verification")

    if proposal["status"] in {"pending", "completed", "failed"}:
        st.caption(
            "AI verification is an evidence-based assessment. "
            "It does not approve or reject the proposal."
        )

        verification_succeeded = False

        if st.button(
            "Start AI Verification",
            key=f"verify_{selected_id}",
            type="primary",
            use_container_width=True,
        ):
            connection = None

            try:
                verification_input = PlannerInput(
                    proposal_id=str(selected_id),
                    article_title=proposal["article_title"],
                    language_code=proposal["language_code"],
                    edit_summary=proposal["edit_summary"] or "",
                    old_text=proposal["original_text"] or "",
                    proposed_text=proposal["proposed_text"],
                )

                with st.spinner(
                    "Running AI verification. This may take some time..."
                ):
                    connection = get_database_connection()
                    verify_proposal(
                        proposal=verification_input,
                        connection=connection,
                    )

                st.success("AI verification completed.")
                verification_succeeded = True

            except Exception as exc:
                st.error(f"AI verification failed: {exc}")

            finally:
                if connection is not None:
                    connection.close()

            if verification_succeeded:
                st.rerun()

    elif proposal["status"] == "running":
        st.info("AI verification is already running for this proposal.")

    else:
        st.info(
            "AI verification cannot be started for a finalized proposal."
        )

    st.divider()
    st.subheader("Previous human reviews")

    try:
        review_history = get_review_history(int(selected_id))
    except Exception as exc:
        st.error(f"Could not load review history: {exc}")
        review_history = []

    if not review_history:
        st.caption("No previous human reviews.")
    else:
        for review in review_history:
            reviewed_at = review["reviewed_at"]
            reviewed_label = (
                reviewed_at.strftime("%Y-%m-%d %H:%M:%S")
                if reviewed_at
                else "Unknown"
            )

            with st.container(border=True):
                st.markdown(
                    f"**{review['action'].upper()}** "
                    f"| Review #{review['review_id']}"
                )
                st.caption(
                    f"Reviewer: {review['reviewer_name'] or 'Unknown'} "
                    f"| {reviewed_label}"
                )
                st.write(
                    review["reviewer_comment"] or "No comment recorded."
                )

    st.divider()
    st.subheader("Human review decision")

    if proposal["status"] in {"approved", "rejected"}:
        st.warning("This proposal already has a final human decision.")

    elif proposal["status"] not in {"pending", "completed", "failed"}:
        st.info("This proposal cannot be reviewed in its current status.")

    else:
        reviewer_name = st.text_input(
            "Reviewer name",
            key=f"reviewer_name_{selected_id}",
        )

        reviewer_comment = st.text_area(
            "Review justification",
            key=f"review_comment_{selected_id}",
            placeholder="Explain why this edit should be approved or rejected.",
        )

        st.caption(
            "AI assessments are advisory. The final decision belongs "
            "to the human reviewer."
        )

        approve_col, reject_col = st.columns(2)

        with approve_col:
            approve_clicked = st.button(
                "Approve proposal",
                key=f"approve_{selected_id}",
                type="primary",
                use_container_width=True,
            )

        with reject_col:
            reject_clicked = st.button(
                "Reject proposal",
                key=f"reject_{selected_id}",
                use_container_width=True,
            )

        if approve_clicked or reject_clicked:
            action = "approved" if approve_clicked else "rejected"

            try:
                review_id = submit_review(
                    proposal_id=int(selected_id),
                    reviewer_name=reviewer_name,
                    action=action,
                    reviewer_comment=reviewer_comment,
                )

                st.success(
                    f"Proposal {action}. Review #{review_id} saved."
                )

                st.session_state.pop("review_queue_selection", None)
                st.rerun()

            except ValueError as exc:
                st.error(str(exc))

            except Exception as exc:
                st.error(f"Could not save human review: {exc}")
