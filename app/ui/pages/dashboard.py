import streamlit as st

from app.services.dashboard_service import get_dashboard_metrics


def render_dashboard():
    st.title("Verification Dashboard")
    st.write(
        "Monitor proposed Wikipedia edits, verification activity, "
        "and human review decisions."
    )

    if st.button("Refresh dashboard"):
        st.rerun()

    try:
        metrics = get_dashboard_metrics()
    except Exception as exc:
        st.error(f"Could not load dashboard metrics: {exc}")
        return

    st.subheader("Knowledge base and proposals")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Indexed articles",
        f"{metrics['article_count']:,}",
    )
    col2.metric(
        "Total proposals",
        f"{metrics['proposal_total']:,}",
    )
    col3.metric(
        "Verification runs",
        f"{metrics['run_total']:,}",
    )

    st.divider()
    st.subheader("Proposal status")

    proposal_statuses = metrics["proposal_statuses"]

    proposal_columns = st.columns(3)

    proposal_labels = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    for index, (status, label) in enumerate(proposal_labels):
        proposal_columns[index % 3].metric(
            label,
            f"{proposal_statuses.get(status, 0):,}",
        )

    st.divider()
    st.subheader("Verification run status")

    run_statuses = metrics["run_statuses"]

    run_columns = st.columns(4)

    for index, status in enumerate(
        ["pending", "running", "completed", "failed"]
    ):
        run_columns[index].metric(
            status.capitalize(),
            f"{run_statuses.get(status, 0):,}",
        )

    st.divider()
    st.subheader("Human review activity")

    review_actions = metrics["review_actions"]

    review_columns = st.columns(3)

    review_columns[0].metric(
        "Total review actions",
        f"{metrics['review_total']:,}",
    )
    review_columns[1].metric(
        "Approved",
        f"{review_actions.get('approved', 0):,}",
    )
    review_columns[2].metric(
        "Rejected",
        f"{review_actions.get('rejected', 0):,}",
    )

    st.caption(
        "AI verification provides evidence and recommendations. "
        "Final publication decisions remain with human reviewers."
    )