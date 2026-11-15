import streamlit as st

from app.services.history_service import (
    get_verification_run_details,
    list_verification_runs,
)


def render_history():
    st.title("Verification History")
    st.write(
        "Review previous verification runs and their execution details."
    )

    status_filter = st.selectbox(
        "Filter by run status",
        options=["All", "completed", "failed", "running", "pending"],
    )

    if st.button("Refresh history"):
        st.rerun()

    try:
        runs = list_verification_runs(
            status=None if status_filter == "All" else status_filter,
            limit=50,
        )
    except Exception as exc:
        st.error(f"Could not load verification history: {exc}")
        return

    if not runs:
        st.info("No verification runs match this filter.")
        return

    st.caption(f"{len(runs)} verification run(s) displayed")

    for run in runs:
        started_at = run["started_at"]
        completed_at = run["completed_at"]

        started_label = (
            started_at.strftime("%Y-%m-%d %H:%M:%S")
            if started_at
            else "Unknown"
        )

        completed_label = (
            completed_at.strftime("%Y-%m-%d %H:%M:%S")
            if completed_at
            else "Not completed"
        )

        with st.container(border=True):
            left, right = st.columns([4, 1])

            with left:
                st.subheader(run["article_title"])
                st.caption(
                    f"Run #{run['run_id']} · "
                    f"Proposal #{run['proposal_id']} · "
                    f"{run['language_code'].upper()}"
                )

                st.write(f"**Started:** {started_label}")
                st.write(f"**Completed:** {completed_label}")

                st.caption(
                    f"LLM: {run['llm_model'] or 'Not recorded'}"
                )
                st.caption(
                    f"Embedding model: "
                    f"{run['embedding_model'] or 'Not recorded'}"
                )

            with right:
                st.markdown(f"**{run['status'].upper()}**")

            if run["error_message"]:
                with st.expander("Execution error"):
                    st.error(run["error_message"])
            with st.expander("View audit details"):
                try:
                    details = get_verification_run_details(
                        int(run["run_id"])
                    )
                except Exception as exc:
                    st.error(f"Could not load audit details: {exc}")
                    continue

                if not details or not details["claims"]:
                    st.info("No claim decisions have been recorded.")
                    continue

                for claim in details["claims"]:
                    with st.container(border=True):
                        st.markdown(
                            f"**Claim #{claim['claim_id']}**"
                        )
                        st.write(claim["claim_text"])

                        st.write(
                            f"**Verdict:** {claim['verdict'].upper()}"
                        )

                        confidence = claim["confidence"]
                        if confidence is not None:
                            st.write(
                                f"**Confidence:** "
                                f"{float(confidence):.1%}"
                            )

                        st.write(
                            "**Human review required:** "
                            f"{'Yes' if claim['requires_human_review'] else 'No'}"
                        )

                        if claim["explanation"]:
                            st.markdown("**Decision explanation**")
                            st.write(claim["explanation"])

                        if claim["recommendation"]:
                            st.markdown("**Recommendation**")
                            st.write(claim["recommendation"])

                        st.markdown(
                            f"**Evidence ({len(claim['evidence'])})**"
                        )

                        if not claim["evidence"]:
                            st.caption("No linked evidence recorded.")

                        for evidence in claim["evidence"]:
                            st.markdown(
                                f"- **{evidence['evidence_relation']}** — "
                                f"[{evidence['source_title'] or 'Untitled source'}]"
                                f"({evidence['source_url']})"
                            )

                            if evidence["publisher"]:
                                st.caption(
                                    f"Publisher: {evidence['publisher']}"
                                )

                            if evidence["relevant_excerpt"]:
                                st.write(evidence["relevant_excerpt"])

                            if evidence["explanation"]:
                                st.caption(evidence["explanation"])

                        st.markdown(
                            f"**Critique findings ({len(claim['critiques'])})**"
                        )

                        if not claim["critiques"]:
                            st.caption("No critique findings recorded.")

                        for finding in claim["critiques"]:
                            st.markdown(
                                f"- **Round {finding['round_number']} · "
                                f"{finding['severity'].upper()} · "
                                f"{finding['issue_type']}**"
                            )
                            st.write(finding["objection"])

                            if finding["requires_reassessment"]:
                                st.caption(
                                    "This finding required reassessment."
                                )

                        if claim["verification_history"]:
                            with st.expander("Agent verification history"):
                                st.json(
                                    claim["verification_history"]
                                )