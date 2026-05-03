"""Notes page — markdown notes optionally attached to a ticker or run."""

from __future__ import annotations

import streamlit as st

from gui import storage

st.set_page_config(page_title="Notes · TradingAgents", layout="wide")
storage.init_db()

st.title("Notes")

# ---- New note form -----------------------------------------------------
with st.expander("➕ New note", expanded=False):
    with st.form("new_note", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        title = c1.text_input("Title")
        ticker = c2.text_input("Ticker (optional)").strip().upper() or None
        body = st.text_area("Body (markdown)", height=180)
        tags = st.text_input("Tags (comma-separated)")
        if st.form_submit_button("Save", type="primary"):
            if not title.strip() or not body.strip():
                st.warning("Title and body are required.")
            else:
                storage.add_note(title=title.strip(), body=body, ticker=ticker,
                                 tags=tags or None)
                st.success("Saved.")
                st.rerun()

# ---- Filter bar --------------------------------------------------------
fc1, fc2 = st.columns([3, 1])
query = fc1.text_input("Search title / body / tags")
ticker_filter = fc2.text_input("Ticker filter").strip().upper() or None

notes = storage.list_notes(ticker=ticker_filter, query=query or None)

# ---- List + edit -------------------------------------------------------
if not notes:
    st.info("No notes match. Use **New note** above to add one.")
    st.stop()

for n in notes:
    header = f"**{n['title']}**"
    badges = []
    if n.get("ticker"):
        badges.append(f"`{n['ticker']}`")
    if n.get("tags"):
        badges.append(f"_{n['tags']}_")
    badges.append(n["updated_at"])
    header += "  ·  " + "  ·  ".join(badges)

    with st.expander(header):
        st.markdown(n["body"])
        col1, col2 = st.columns([1, 1])
        if col1.button("Edit", key=f"edit_{n['id']}"):
            st.session_state[f"editing_{n['id']}"] = True
        if col2.button("Delete", key=f"del_{n['id']}", type="secondary"):
            storage.delete_note(n["id"])
            st.rerun()

        if st.session_state.get(f"editing_{n['id']}"):
            with st.form(f"edit_form_{n['id']}"):
                new_title = st.text_input("Title", value=n["title"])
                new_body = st.text_area("Body", value=n["body"], height=180)
                new_tags = st.text_input("Tags", value=n.get("tags") or "")
                cs = st.columns(2)
                save = cs[0].form_submit_button("Save", type="primary")
                cancel = cs[1].form_submit_button("Cancel")
                if save:
                    storage.update_note(n["id"], title=new_title, body=new_body,
                                        tags=new_tags or None)
                    st.session_state[f"editing_{n['id']}"] = False
                    st.rerun()
                if cancel:
                    st.session_state[f"editing_{n['id']}"] = False
                    st.rerun()
