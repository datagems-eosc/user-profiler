import uuid
from datetime import date, datetime, timedelta, timezone

import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

INACTIVITY_MINUTES = 5

_API_OPTIONS = {
    "Local": "http://localhost:8000",
    "DataGEMS (dev)": "https://datagems-dev.scayle.es/up",
}

st.set_page_config(page_title="User Profiler", layout="wide")

with st.sidebar:
    st.markdown("### API endpoint")
    _api_choice = st.radio(
        "API endpoint",
        list(_API_OPTIONS.keys()),
        key="api_choice",
        label_visibility="collapsed",
    )
    st.caption(_API_OPTIONS[_api_choice])

API_BASE = _API_OPTIONS[_api_choice]


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _get(path: str, timeout: int = 5):
    r = requests.get(f"{API_BASE}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict):
    r = requests.post(f"{API_BASE}{path}", json=payload, timeout=5)
    r.raise_for_status()
    return r.json()


def _patch(path: str, payload: dict):
    r = requests.patch(f"{API_BASE}{path}", json=payload, timeout=5)
    r.raise_for_status()
    return r.json()


def _delete(path: str):
    r = requests.delete(f"{API_BASE}{path}", timeout=5)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _nav(page: str, user_id: str = None):
    st.session_state.page = page
    st.session_state.selected_user_id = user_id
    # Reset per-page dynamic counters when navigating away
    for key in list(st.session_state.keys()):
        if key.startswith(("_pub_count", "_sess_count", "_orcid_data", "_gen_kw")):
            del st.session_state[key]


if "page" not in st.session_state:
    st.session_state.page = "list"
if "selected_user_id" not in st.session_state:
    st.session_state.selected_user_id = None


# ---------------------------------------------------------------------------
# API availability check  (stops rendering if the server is unreachable)
# ---------------------------------------------------------------------------

try:
    requests.get(f"{API_BASE}/users", timeout=2)
except (ConnectionError, Timeout):
    st.error(
        "Cannot connect to the User Profiler API.  "
        "Make sure the server is running:  \n"
        "```\nuvicorn up_api.main:app --reload\n```"
    )
    st.stop()


# ---------------------------------------------------------------------------
# ORCID raw-profile parser
# ---------------------------------------------------------------------------

def _parse_llm_keywords(text: str) -> list[str]:
    """Parses LLM keyword output — handles Python list literals and comma/newline lists."""
    import re, ast
    try:
        parsed = ast.literal_eval(text.strip())
        if isinstance(parsed, list):
            return [str(k).strip() for k in parsed if str(k).strip()]
    except (ValueError, SyntaxError):
        pass
    parts = re.split(r"[\n,]+", text)
    return [
        re.sub(r"^[\s\-\*\•\d\.]+", "", p).strip()
        for p in parts
        if re.sub(r"^[\s\-\*\•\d\.]+", "", p).strip()
    ]


def _parse_orcid_raw(raw: dict, orcid_id: str) -> dict:
    kw_list = (raw.get("person") or {}).get("keywords", {}).get("keyword", [])
    keywords = [{"value": k["content"]} for k in kw_list if k.get("content")]

    pubs = []
    groups = ((raw.get("activities-summary") or {})
              .get("works", {}).get("group", []))
    for group in groups:
        for summary in group.get("work-summary", []):
            title = ((summary.get("title") or {})
                     .get("title", {}).get("value", ""))
            jt = summary.get("journal-title")
            journal = jt.get("value", "") if jt else ""
            pd_ = summary.get("publication-date") or {}
            yr = pd_.get("year")
            year = int(yr["value"]) if yr and yr.get("value") else 0
            doi = ""
            for eid in (summary.get("external-ids") or {}).get("external-id", []):
                if eid.get("external-id-type") == "doi":
                    doi = eid.get("external-id-value", "")
                    break
            if title:
                pubs.append({
                    "title": title, "doi": doi,
                    "journal": journal, "year": year, "authors": [],
                })

    return {"id": orcid_id, "keywords": keywords, "publications": pubs}


# ---------------------------------------------------------------------------
# Shared form renderer  (used by both Create and Edit pages)
# ---------------------------------------------------------------------------

def _render_user_form(defaults: dict = None) -> dict | None:
    """
    Renders all editable user fields. Returns the payload dict when the form
    is submitted, or None while the user is still filling it in.
    """
    d = defaults or {}
    d_orc = d.get("orcid") or {}
    d_loc = d.get("location") or {}

    # -- Basic fields --
    _raw_dob = d.get("dateOfBirth")
    _dob_default = None
    if _raw_dob:
        try:
            _dob_default = datetime.fromisoformat(str(_raw_dob)).date()
        except (ValueError, TypeError):
            pass

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name *", value=d.get("name", ""))
        dob = st.date_input("Date of birth", value=_dob_default,
                            min_value=date(1909, 1, 1), max_value=date.today())
        affiliation = st.text_input("Affiliation *", value=d.get("affiliation", ""))
    with col2:
        surname = st.text_input("Surname *", value=d.get("surname", ""))
        email = st.text_input("Email *", value=d.get("email", ""))

    st.divider()

    # -- Location --
    with st.expander("Location", expanded=bool(d_loc)):
        add_loc = st.checkbox("Include location", value=bool(d_loc))
        if add_loc:
            lc1, lc2 = st.columns(2)
            with lc1:
                city = st.text_input("City", value=d_loc.get("city", ""))
            with lc2:
                country = st.text_input("Country", value=d_loc.get("country", ""))

    # -- ORCID --
    with st.expander("ORCID", expanded=bool(d_orc)):
        add_orc = st.checkbox("Include ORCID", value=bool(d_orc))
        if add_orc:
            # Seed session state from existing data when entering edit mode
            if "_orcid_data" not in st.session_state and d_orc:
                st.session_state._orcid_data = d_orc

            orcid_id = st.text_input("ORCID ID", value=d_orc.get("id", ""))

            if st.button("Fetch from ORCID"):
                if orcid_id:
                    try:
                        raw = _get(f"/orcid/{orcid_id}")
                        st.session_state._orcid_data = _parse_orcid_raw(raw, orcid_id)
                        st.success("ORCID data fetched.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not fetch ORCID data: {e}")
                else:
                    st.warning("Enter an ORCID ID first.")

            fetched = st.session_state.get("_orcid_data")
            if fetched:
                kws = fetched.get("keywords", [])
                pubs = fetched.get("publications", [])
                if kws:
                    st.write("**Keywords:** " + " · ".join(k["value"] for k in kws))
                st.write(f"**Publications:** {len(pubs)} found")
                for pub in pubs[:5]:
                    st.caption(f"- {pub['title']} ({pub.get('year') or '?'})")
                if len(pubs) > 5:
                    st.caption(f"  ... and {len(pubs) - 5} more")

    st.divider()

    # -- Submit --
    if st.button("Save", type="primary"):
        if not all([name, surname, email, affiliation]):
            st.warning("Please fill in all required fields (marked with *).")
            return None

        payload: dict = {
            "name": name, "surname": surname,
            "email": email, "affiliation": affiliation,
        }
        if dob:
            payload["dateOfBirth"] = datetime(dob.year, dob.month, dob.day).isoformat()

        if add_loc and city and country:
            payload["location"] = {"city": city, "country": country}

        if add_orc and orcid_id:
            fetched = st.session_state.get("_orcid_data") or {}
            payload["orcid"] = {
                "id": orcid_id,
                "keywords": fetched.get("keywords", []),
                "publications": fetched.get("publications", []),
            }

        return payload

    return None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_list():
    st.title("Users")

    col_title, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("+ Create user", use_container_width=True):
            _nav("create")
            st.rerun()

    try:
        data = _get("/users")
    except Exception as e:
        st.error(f"Could not load user list: {e}")
        return

    count = data["count"]
    users = data["users"]

    st.caption(f"{count} user{'s' if count != 1 else ''} registered")

    if not users:
        st.info("No users yet. Click **+ Create user** to add the first one.")
        return

    header = st.columns([2, 2, 3, 1, 1, 1])
    header[0].markdown("**Name**")
    header[1].markdown("**Surname**")
    header[2].markdown("**User ID**")
    header[3].markdown("**View**")
    header[4].markdown("**Edit**")
    header[5].markdown("**Delete**")
    st.divider()

    for u in users:
        uid = u["userId"]
        row = st.columns([2, 2, 3, 1, 1, 1])
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
                _delete(f"/user/{uid}")
                st.rerun()
            except Exception as e:
                st.error(f"Could not delete user: {e}")


def page_view():
    user_id = st.session_state.selected_user_id

    if st.button("← Back to list"):
        _nav("list")
        st.rerun()

    try:
        user = _get(f"/user/{user_id}")
    except Exception as e:
        st.error(f"Could not load user: {e}")
        return

    if "message" in user:
        st.warning(user["message"])
        return

    # Header
    col_name, col_edit = st.columns([5, 1])
    with col_name:
        st.title(f"{user['name']} {user['surname']}")
        st.caption(f"ID: {user['userId']}")
    with col_edit:
        if st.button("Edit", type="primary"):
            _nav("edit", user_id)
            st.rerun()

    st.divider()

    # Basic info
    c1, c2, c3 = st.columns(3)
    _dob_raw = user.get("dateOfBirth")
    _dob_display = datetime.fromisoformat(str(_dob_raw)).strftime("%d %b %Y") if _dob_raw else "—"
    c1.metric("Date of birth", _dob_display)
    c2.metric("Email", user["email"])
    c3.metric("Affiliation", user["affiliation"])

    # Location
    if user.get("location"):
        st.subheader("Location")
        loc = user["location"]
        st.write(f"{loc['city']}, {loc['country']}")

    # Keywords
    kws = user.get("keywords", [])
    col_kw, col_kw_btn = st.columns([5, 1])
    with col_kw:
        st.subheader("Keywords")
    if kws:
        with col_kw_btn:
            if st.button("Clear all", key="btn_clear_kw"):
                try:
                    _patch(f"/user/{user_id}", {"keywords": []})
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not clear keywords: {e}")
        tags_html = " ".join(
            f'<span style="background:#e8f4f8; border:1px solid #aecfe0; border-radius:14px; '
            f'padding:3px 12px; margin:3px; display:inline-block; font-size:0.9rem;">'
            f'{k["value"]}</span>'
            for k in kws
        )
        st.markdown(tags_html, unsafe_allow_html=True)
    else:
        st.caption("No keywords yet.")

    # ORCID
    if user.get("orcid"):
        st.subheader("ORCID")
        orc = user["orcid"]
        st.write(f"**ID:** {orc['id']}")

        if orc.get("publications"):
            st.write(f"**Publications ({len(orc['publications'])}):**")
            for pub in orc["publications"]:
                with st.expander(pub["title"]):
                    st.write(f"**DOI:** {pub['doi']}")
                    st.write(f"**Journal:** {pub['journal']}  |  **Year:** {pub['year']}")
                    if pub.get("authors"):
                        st.write("**Authors:** " +
                                 ", ".join(a["fullName"] for a in pub["authors"]))

    # Sessions
    if user.get("sessions"):
        st.subheader(f"Sessions ({len(user['sessions'])})")
        for s in user["sessions"]:
            status = "  [extracted]" if s.get("extracted") else ""
            label = f"{s['sessionId']}  —  {s['startTime']}{status}"
            with st.expander(label):
                if s.get("endTime"):
                    st.write(f"**End:** {s['endTime']}")
                if s.get("queries"):
                    for q in s["queries"]:
                        ts = f"  `{q['typedAt']}`" if q.get("typedAt") else ""
                        st.write(f"- {q['text']}{ts}")
                if s.get("extracted"):
                    if st.button("Mark as unseen", key=f"btn_unseen_{s['sessionId']}"):
                        sessions = user["sessions"]
                        for sess in sessions:
                            if sess["sessionId"] == s["sessionId"]:
                                sess["extracted"] = False
                                break
                        try:
                            _patch(f"/user/{user_id}", {"sessions": sessions})
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not update session: {e}")

    # Keyword generation from sessions
    all_queries = [
        q for s in user.get("sessions", []) for q in s.get("queries", [])
    ]
    if all_queries:
        st.divider()
        st.subheader("Generate keywords from sessions")

        if st.button("Generate", key="btn_gen_kw"):
            st.session_state._gen_kw_user = user_id
            st.session_state.pop("_gen_kw_result", None)
            st.session_state.pop("_gen_kw_all_extracted", None)
            unextracted = [
                s for s in user.get("sessions", [])
                if not s.get("extracted") and s.get("queries")
            ]
            if not unextracted:
                st.session_state._gen_kw_all_extracted = True
            else:
                try:
                    resp = _get(f"/user/{user_id}/generate-keywords", timeout=130)
                    if "keywords" in resp:
                        st.session_state._gen_kw_result = resp["keywords"]
                    else:
                        st.error(resp.get("error", "Generation failed."))
                except Exception as e:
                    st.error(f"Could not generate keywords: {e}")

        if st.session_state.get("_gen_kw_user") == user_id:
            if st.session_state.get("_gen_kw_all_extracted"):
                st.info("All session keywords have already been extracted.")
            raw_kw = st.session_state.get("_gen_kw_result")
            if raw_kw:
                keywords = _parse_llm_keywords(raw_kw)
                st.write("**Generated keywords:**")
                for kw in keywords:
                    st.write(f"- {kw}")

                if st.button("Accept & save", key="btn_accept_kw", type="primary"):
                    sessions = user.get("sessions", [])
                    for s in sessions:
                        if not s.get("extracted") and s.get("queries"):
                            s["extracted"] = True
                    try:
                        _patch(f"/user/{user_id}", {
                            "keywords": [{"value": kw} for kw in keywords],
                            "sessions": sessions,
                        })
                        st.session_state.pop("_gen_kw_result", None)
                        st.success("Keywords saved and sessions marked as extracted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save keywords: {e}")


def page_create():
    if st.button("← Back to list"):
        _nav("list")
        st.rerun()

    st.title("Create user")

    payload = _render_user_form()
    if payload is not None:
        try:
            result = _post("/user", payload)
            st.success(f"User created with ID `{result['userId']}`")
            _nav("view", result["userId"])
            st.rerun()
        except Exception as e:
            st.error(f"Failed to create user: {e}")


def page_edit():
    user_id = st.session_state.selected_user_id

    if st.button("← Back"):
        _nav("view", user_id)
        st.rerun()

    st.title("Edit user")
    st.caption(f"ID: {user_id}")

    try:
        current = _get(f"/user/{user_id}")
    except Exception as e:
        st.error(f"Could not load user: {e}")
        return

    if "message" in current:
        st.warning(current["message"])
        return

    payload = _render_user_form(defaults=current)
    if payload is not None:
        try:
            _patch(f"/user/{user_id}", payload)
            st.success("User updated.")
            _nav("view", user_id)
            st.rerun()
        except Exception as e:
            st.error(f"Failed to update user: {e}")


# ---------------------------------------------------------------------------
# Session inactivity helper
# ---------------------------------------------------------------------------

def _close_if_inactive(user_id: str, session: dict, sessions: list) -> bool:
    """
    Sets endTime on the session and PATCHes the user if the last activity
    was more than INACTIVITY_MINUTES ago. Returns True when closed.
    """
    queries = session.get("queries", [])
    last_ts_str = queries[-1].get("typedAt") if queries else session.get("startTime")
    if not last_ts_str:
        return False

    last_ts = datetime.fromisoformat(last_ts_str)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    if (datetime.now(timezone.utc) - last_ts).total_seconds() > INACTIVITY_MINUTES * 60:
        session["endTime"] = (last_ts + timedelta(minutes=INACTIVITY_MINUTES)).isoformat()
        _patch(f"/user/{user_id}", {"sessions": sessions})
        return True
    return False


# ---------------------------------------------------------------------------
# Chat page
# ---------------------------------------------------------------------------

def page_chat():
    st.title("Chat")

    try:
        data = _get("/users")
    except Exception as e:
        st.error(f"Could not load users: {e}")
        return

    users = data["users"]
    if not users:
        st.info("No users yet. Create one in the **Users** tab.")
        return

    labels = [f"{u['name']} {u['surname']}" for u in users]
    idx = st.selectbox(
        "Select user",
        range(len(users)),
        format_func=lambda i: labels[i],
        key="chat_user_select",
    )
    selected_user_id = users[idx]["userId"]

    if st.session_state.get("_chat_user_id") != selected_user_id:
        st.session_state._chat_user_id = selected_user_id

    try:
        user = _get(f"/user/{selected_user_id}")
    except Exception as e:
        st.error(f"Could not load user profile: {e}")
        return

    sessions = user.get("sessions", [])
    # Most-recent open session (no endTime)
    active = next((s for s in reversed(sessions) if not s.get("endTime")), None)

    # Close it if idle for too long
    if active and _close_if_inactive(selected_user_id, active, sessions):
        active = None

    st.divider()
    if active:
        st.caption(
            f"Session `{active['sessionId'][:8]}...`  "
            f"started {active['startTime']}"
        )
        for q in active.get("queries", []):
            with st.chat_message("user"):
                st.write(q["text"])
                if q.get("typedAt"):
                    st.caption(q["typedAt"])
    else:
        st.caption("No active session yet. Send a message to start one.")

    if prompt := st.chat_input("Type a message..."):
        new_query = {
            "text": prompt,
            "typedAt": datetime.now(timezone.utc).isoformat(),
        }

        # Re-fetch to avoid overwriting concurrent changes
        user = _get(f"/user/{selected_user_id}")
        sessions = user.get("sessions", [])
        active = next((s for s in reversed(sessions) if not s.get("endTime")), None)

        if active:
            active.setdefault("queries", []).append(new_query)
        else:
            sessions.append({
                "sessionId": str(uuid.uuid4()),
                "startTime": datetime.now(timezone.utc).isoformat(),
                "queries": [new_query],
            })

        try:
            _patch(f"/user/{selected_user_id}", {"sessions": sessions})
        except Exception as e:
            st.error(f"Could not save message: {e}")
        st.rerun()


# ---------------------------------------------------------------------------
# Top-level tabs
# ---------------------------------------------------------------------------

tab_users, tab_chat = st.tabs(["Users", "Chat"])

with tab_users:
    page = st.session_state.page
    if page == "list":
        page_list()
    elif page == "view":
        page_view()
    elif page == "create":
        page_create()
    elif page == "edit":
        page_edit()

with tab_chat:
    page_chat()
