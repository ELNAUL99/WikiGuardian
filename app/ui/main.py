import streamlit as st

from app.ui.pages.dashboard import render_dashboard
from app.ui.pages.history import render_history
from app.ui.pages.review_queue import render_review_queue
from app.ui.pages.submit_edit import render_submit_edit
from app.ui.pages.wikipedia import render_wikipedia


st.set_page_config(
    page_title="WikiGuardian",
    page_icon="WG",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128, 128, 128, 0.2);
        }

        .brand-subtitle {
            color: #8b949e;
            font-size: 0.85rem;
            margin-top: -12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.markdown("# WikiGuardian")
    st.markdown(
        '<p class="brand-subtitle">AI-powered Wikipedia edit verification</p>',
        unsafe_allow_html=True,
    )

    st.divider()

    page = st.radio(
        "Navigation",
        [
            "Wikipedia (Live Demo)",
            "Dashboard",
            "Submit Edit",
            "Review Queue",
            "History",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.caption("Seven-agent verification system")
    st.caption("Human-in-the-loop decisions")


if page == "Wikipedia (Live Demo)":
    render_wikipedia()

elif page == "Dashboard":
    render_dashboard()

elif page == "Submit Edit":
    render_submit_edit()

elif page == "Review Queue":
    render_review_queue()

elif page == "History":
    render_history()


st.divider()
st.caption(
    "WikiGuardian | AI-assisted verification | "
    "Final publication decisions remain with human reviewers."
)