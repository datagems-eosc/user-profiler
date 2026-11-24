"""
Users tab: 
    - list
    - view
    - create and edit users
    - keywords
        --> Those stored in grafeo
"""
import uuid
from datetime import datetime

import requests
import streamlit as st

from ui_local import client as api
from ui_local import dmm
from ui_local.components import parse_llm_keywords, render_keyword_tags, render_user_form


def render():
    st.session_state.setdefault("page", "list")
    st.session_state.setdefault("selected_user_id", None)
    PAGES[st.session_state.page]()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nav(page: str, user_id: str = None):
    st.session_state.page = page
    st.session_state.selected_user_id = user_id
    # Reset per-page state when navigating away
    for key in list(st.session_state.keys()):
        if key.startswith(("_orcid_data", "_gen_kw")):
            del st.session_state[key]


def _load_user(user_id: str) -> dict | None:
    """The user, or None after showing the error."""
    try:
        return api.get(f"/user/{user_id}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            st.warning(api.error_detail(e))
        else:
            st.error(f"Could not load user: {e}")
    except Exception as e:
        st.error(f"Could not load user: {e}")
    return None


def _weighted_keywords(user_id: str) -> list[dict] | None:
    """Keywords with weights, or None on API versions without the endpoint."""
    try:
        return api.get(f"/user/{user_id}/keywords")["keywords"]
    except Exception:
        return None


def _valid_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def page_list():
    st.title("Users")

    _, col_btn = st.columns([5, 1])
    if col_btn.button("+ Create user", use_container_width=True):
        _nav("create")
        st.rerun()

    if api.dmm_mode():
        dmm.add_dmm_user()

    try:
        data = api.get("/users")
    except Exception as e:
        st.error(f"Could not load user list: {e}")
        return

    count, users = data["count"], data["users"]
    st.caption(f"{count} user{'s' if count != 1 else ''} registered")
    if not users:
        st.info("No users yet. Click **+ Create user** to add the first one.")
        return

    widths = [2, 2, 3, 1, 1, 1]
    for col, title in zip(st.columns(widths), ["Name", "Surname", "User ID", "View", "Edit", "Delete"]):
        col.markdown(f"**{title}**")
    st.divider()

    for u in users:
        uid = u["userId"]
        row = st.columns(widths)
        row[0].write(u["name"])
        row[1].write(u["surname"])
        row[2].code(uid)
        if row[3].button("View", key=f"view_{uid}"):
            _nav("view", uid)
            st.rerun()
        if row[4].button("Edit", key=f"edit_{uid}"):
            _nav("edit", uid)
            st.rerun()
        if row[5].button("Delete", key=f"del_{uid}", type="primary"):
            try:
                api.delete(f"/user/{uid}")
                st.rerun()
            except Exception as e:
                st.error(f"Could not delete user: {e}")


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

def page_view():
    user_id = st.session_state.selected_user_id

    if st.button("← Back to list"):
        _nav("list")
        st.rerun()

    if (user := _load_user(user_id)) is None:
        return

    col_name, col_edit = st.columns([5, 1])
    with col_name:
        st.title(f"{user['name']} {user['surname']}")
        st.caption(f"ID: {user['userId']}")
    if col_edit.button("Edit", type="primary"):
        _nav("edit", user_id)
        st.rerun()

    st.divider()
    _render_basic_info(user)
    _render_sessions(user)

    # Queries the DMM has logged under this user's ID
    saved = dmm.saved_query_times(user)
    if api.dmm_mode():
        dmm.live_dmm(user_id, saved)
        dmm_queries = []  # only used in _render_generate as "DMM mode or dmm_queries"
    else:
        dmm_queries = dmm.render_dmm_queries(user_id, saved)
        dmm.render_refresh_status(user_id)

    _render_keywords(user)
    _render_generate(user, has_dmm_queries=api.dmm_mode() or bool(dmm_queries))


def _render_basic_info(user: dict):
    c1, c2, c3 = st.columns(3)
    dob = user.get("dateOfBirth")
    c1.metric("Date of birth", datetime.fromisoformat(str(dob)).strftime("%d %b %Y") if dob else "—")
    c2.metric("Email", user["email"])
    c3.metric("Affiliation", user["affiliation"])

    if loc := user.get("location"):
        st.subheader("Location")
        st.write(f"{loc['city']}, {loc['country']}")

    if orc := user.get("orcid"):
        st.subheader("ORCID")
        st.write(f"**ID:** {orc['id']}")
        if orc.get("publications"):
            st.write(f"**Publications ({len(orc['publications'])}):**")
            for pub in orc["publications"]:
                with st.expander(pub["title"]):
                    st.write(f"**DOI:** {pub['doi']}")
                    st.write(f"**Journal:** {pub['journal']}  |  **Year:** {pub['year']}")
                    if pub.get("authors"):
                        st.write("**Authors:** " + ", ".join(a["fullName"] for a in pub["authors"]))


def _render_sessions(user: dict):
    sessions = user.get("sessions")
    if not sessions:
        return
    st.subheader(f"Sessions ({len(sessions)})")
    for s in sessions:
        status = "  [extracted]" if s.get("extracted") else ""
        with st.expander(f"{s['sessionId']}  —  {s['startTime']}{status}"):
            if s.get("endTime"):
                st.write(f"**End:** {s['endTime']}")
            for q in s.get("queries", []):
                ts = f"  `{q['typedAt']}`" if q.get("typedAt") else ""
                st.write(f"- {q['text']}{ts}")
            if s.get("extracted") and st.button("Mark as unseen", key=f"btn_unseen_{s['sessionId']}"):
                s["extracted"] = False
                try:
                    api.patch(f"/user/{user['userId']}", {"sessions": sessions})
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not update session: {e}")


def _render_keywords(user: dict):
    user_id = user["userId"]
    kws = user.get("keywords", [])
    col_kw, col_kw_btn = st.columns([5, 1])
    col_kw.subheader("Keywords")
    if not kws:
        st.caption("No keywords yet.")
        return

    if col_kw_btn.button("Clear all", key="btn_clear_kw"):
        try:
            api.patch(f"/user/{user_id}", {"keywords": []})
            st.rerun()
        except Exception as e:
            st.error(f"Could not clear keywords: {e}")

    session_weighted = [k for k in _weighted_keywords(user_id) or [] if k["source"] == "session"]
    if session_weighted:
        render_keyword_tags(session_weighted)
        st.caption("Weight halves every 30 days (by default) since the keyword was last extracted. "
                   "Struck-through keywords have expired: they are no longer sent to other services, "
                   "until they are extracted again.")
    else:
        render_keyword_tags(kws)


def _render_generate(user: dict, has_dmm_queries: bool):
    """Manual keyword generation (GET /generate-keywords), then Accept & save."""
    user_id = user["userId"]
    if not any(s.get("queries") for s in user.get("sessions", [])) and not has_dmm_queries:
        return

    st.divider()
    st.subheader("Generate keywords from sessions")

    if st.button("Generate", key="btn_gen_kw"):
        st.session_state._gen_kw_user = user_id
        st.session_state.pop("_gen_kw_result", None)
        st.session_state.pop("_gen_kw_all_extracted", None)
        unextracted = [s for s in user.get("sessions", []) if not s.get("extracted") and s.get("queries")]
        # The API generates from the DMM queries when there are any, so only stop here without them
        if not unextracted and not has_dmm_queries:
            st.session_state._gen_kw_all_extracted = True
        else:
            try:
                st.session_state._gen_kw_result = api.get(f"/user/{user_id}/generate-keywords", timeout=130)["keywords"]
            except requests.HTTPError as e:
                st.error(f"Could not generate keywords: {api.error_detail(e)}")
            except Exception as e:
                st.error(f"Could not generate keywords: {e}")

    if st.session_state.get("_gen_kw_user") != user_id:
        return

    if st.session_state.get("_gen_kw_all_extracted"):
        st.info("All session keywords have already been extracted.")
    raw_kw = st.session_state.get("_gen_kw_result")
    if raw_kw == []:
        st.info("The LLM found no keywords in these sessions.")
    if raw_kw:
        # Older API versions return the raw LLM text instead of a list
        keywords = parse_llm_keywords(raw_kw) if isinstance(raw_kw, str) else raw_kw
        existing = {k["value"].lower() for k in user.get("keywords", [])}
        st.write("**Generated keywords:**")
        for kw in keywords:
            note = "already saved: its weight will be refreshed" if kw.lower() in existing else "**new**"
            st.write(f"- {kw} ({note})")
        if st.button("Accept & save", key="btn_accept_kw", type="primary"):
            _save_generated(user, keywords, existing)

    if saved := st.session_state.pop("_gen_kw_saved", None):
        st.success(saved)


def _save_generated(user: dict, keywords: list[str], existing: set):
    user_id = user["userId"]
    sessions = user.get("sessions", [])
    for s in sessions:
        if not s.get("extracted") and s.get("queries"):
            s["extracted"] = True
    try:
        try:
            # Appends new keywords and refreshes the ones already saved
            res = api.post(f"/user/{user_id}/keywords", {"keywords": keywords})
            api.patch(f"/user/{user_id}", {"sessions": sessions})
            msg = f"{len(res['added'])} new keyword(s) added, {len(res['refreshed'])} refreshed."
        except requests.HTTPError as e:
            if e.response.status_code not in (404, 405):
                raise
            # Older API without the append endpoint: merge here instead of overwriting
            merged = user.get("keywords", []) + [{"value": kw} for kw in keywords if kw.lower() not in existing]
            api.patch(f"/user/{user_id}", {"keywords": merged, "sessions": sessions})
            msg = "Keywords appended (older API: no timestamps)."
        st.session_state.pop("_gen_kw_result", None)
        st.session_state._gen_kw_saved = msg + " Sessions marked as extracted."
        st.rerun()
    except Exception as e:
        st.error(f"Could not save keywords: {e}")


# ---------------------------------------------------------------------------
# Create / Edit
# ---------------------------------------------------------------------------

def page_create():
    if st.button("← Back to list"):
        _nav("list")
        st.rerun()

    st.title("Create user")

    # Optional: reuse the ID the DMM logs this user's queries under, so keyword generation finds them
    custom_id = st.text_input(
        "User ID (optional)",
        placeholder="Leave empty for a new random ID, or paste the user's DMM ID",
        help="Find a DMM ID in the 'DMM queries' tab (most recent queries by any user).",
    ).strip()

    payload = render_user_form()
    if payload is None:
        return
    if custom_id and not _valid_uuid(custom_id):
        st.error("The user ID must be a lowercase, hyphenated UUID.")
        return
    try:
        result = api.post(f"/user/{custom_id}" if custom_id else "/user", payload)
        _nav("view", result["userId"])
        st.rerun()
    except requests.HTTPError as e:
        # e.g. 409 if a user with this ID already exists
        st.error(f"Failed to create user: {api.error_detail(e)}")
    except Exception as e:
        st.error(f"Failed to create user: {e}")


def page_edit():
    user_id = st.session_state.selected_user_id

    if st.button("← Back"):
        _nav("view", user_id)
        st.rerun()

    st.title("Edit user")
    st.caption(f"ID: {user_id}")

    if (current := _load_user(user_id)) is None:
        return

    payload = render_user_form(defaults=current)
    if payload is not None:
        try:
            api.patch(f"/user/{user_id}", payload)
            _nav("view", user_id)
            st.rerun()
        except Exception as e:
            st.error(f"Failed to update user: {e}")


PAGES = {"list": page_list, "view": page_view, "create": page_create, "edit": page_edit}
