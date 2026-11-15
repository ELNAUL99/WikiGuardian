import streamlit as st

from app.services.article_service import search_articles
from app.services.proposal_service import create_proposal


def render_submit_edit():
    st.title("Submit a Wikipedia Edit")
    st.write(
        "Select an imported article and provide the proposed change. "
        "WikiGuardian will investigate each factual claim."
    )

    st.subheader("1. Select an article")

    language_code = st.selectbox(
        "Article language",
        options=["en", "fi", "sv"],
        format_func=lambda code: {
            "en": "English",
            "fi": "Finnish",
            "sv": "Swedish",
        }[code],
        key="submission_language",
    )

    search_query = st.text_input(
        "Search article titles",
        placeholder="Enter an article title or keyword",
        key="article_search_query",
    )

    if st.button("Search articles", type="secondary"):
        try:
            results = search_articles(
                language_code=language_code,
                query=search_query,
                limit=30,
            )
            st.session_state["article_search_results"] = results
            st.session_state["article_search_language"] = language_code
            st.session_state.pop("selected_article_label", None)
        except Exception as exc:
            st.error(f"Article search failed: {exc}")
            return

    results = st.session_state.get("article_search_results", [])

    if st.session_state.get("article_search_language") != language_code:
        results = []

    if not results:
        st.info("Search for an article to see matching results.")
        return

    article_options = {
        f"{article['title']} (ID: {article['article_id']})": article
        for article in results
    }

    selected_label = st.selectbox(
        "Matching articles",
        options=list(article_options.keys()),
        key="selected_article_label",
    )

    selected_article = article_options[selected_label]

    st.caption(
        f"Wikipedia page ID: {selected_article['wikipedia_page_id']}"
    )

    if selected_article["article_url"]:
        st.markdown(
            f"[Open Wikipedia article]({selected_article['article_url']})"
        )

    st.divider()
    st.subheader("2. Describe the proposed edit")

    with st.form("edit_submission_form"):
        editor_name = st.text_input(
            "Editor name (optional)",
            placeholder="Your name or username",
        )

        edit_summary = st.text_input(
            "Edit summary",
            placeholder="Briefly explain the purpose of this change",
        )

        original_text = st.text_area(
            "Original article text",
            height=180,
            placeholder="Paste the existing article passage...",
        )

        proposed_text = st.text_area(
            "Proposed replacement text",
            height=220,
            placeholder="Paste the replacement passage...",
        )

        submitted = st.form_submit_button(
            "Review submission",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        errors = []

        if not edit_summary.strip():
            errors.append("Enter an edit summary.")

        if not original_text.strip():
            errors.append("Provide the original article text.")

        if not proposed_text.strip():
            errors.append("Provide the proposed replacement text.")

        if (
            original_text.strip()
            and proposed_text.strip()
            and original_text.strip() == proposed_text.strip()
        ):
            errors.append(
                "The proposed text is identical to the original text."
            )

        if errors:
            for error in errors:
                st.error(error)
            return

        st.session_state["edit_submission_draft"] = {
            "article_id": selected_article["article_id"],
            "wikipedia_page_id": selected_article["wikipedia_page_id"],
            "article_title": selected_article["title"],
            "article_url": selected_article["article_url"],
            "language_code": selected_article["language_code"],
            "editor_name": editor_name.strip(),
            "edit_summary": edit_summary.strip(),
            "old_text": original_text.strip(),
            "proposed_text": proposed_text.strip(),
        }

        st.session_state.pop("saved_proposal_id", None)
        st.success("Submission draft captured.")

    draft = st.session_state.get("edit_submission_draft")

    if draft:
        st.divider()
        st.subheader("3. Review and save proposal")

        st.write(
            f"**Article:** {draft['article_title']} "
            f"({draft['language_code']})"
        )
        st.write(f"**Database article ID:** {draft['article_id']}")
        st.write(f"**Edit summary:** {draft['edit_summary']}")

        with st.expander("Review proposed text"):
            st.markdown("**Original text**")
            st.text(draft["old_text"])

            st.markdown("**Proposed text**")
            st.text(draft["proposed_text"])

        saved_proposal_id = st.session_state.get("saved_proposal_id")

        if saved_proposal_id:
            st.success(
                f"Proposal saved successfully. Proposal ID: {saved_proposal_id}"
            )
        else:
            if st.button(
                "Save proposal to MariaDB",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner("Saving proposal..."):
                        proposal_id = create_proposal(
                            article_id=draft["article_id"],
                            original_text=draft["old_text"],
                            proposed_text=draft["proposed_text"],
                            edit_summary=draft["edit_summary"],
                            editor_name=draft["editor_name"],
                        )

                    st.session_state["saved_proposal_id"] = proposal_id
                    st.success(
                        f"Proposal saved successfully. Proposal ID: {proposal_id}"
                    )

                except Exception as exc:
                    st.error(f"Could not save proposal: {exc}")

        st.caption(
            "Saving creates a pending proposal. It does not start "
            "AI verification or publish an edit."
        )