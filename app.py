import base64
import json
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

INACTIVITY_MINUTES = 5

_API_OPTIONS = {
    "Local": "http://localhost:8000",
    "DataGEMS (dev)": "https://datagems-dev.scayle.es/up",
    # Option to use DMM data
    "Local + DMM": "http://localhost:8000",
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

    _token = st.text_input(
        "Keycloak token",
        value=os.getenv("DATAGEMS_TOKEN", ""),
        type="password",
        help="Sent as `Authorization: Bearer <token>`; it needs `user-profiler` or `query-recommender` "
             "in its audience. "
             "Get one from the 'Keycloak token' tab of DataGEMS_LLM_credentials_info.",
    ).strip().removeprefix("Bearer ").strip()

API_BASE = _API_OPTIONS[_api_choice]
# flag for DMM option
DMM_MODE = _api_choice == "Local + DMM"
HEADERS = {"Authorization": f"Bearer {_token}"} if _token else {}


def _token_problem(token: str) -> str | None:
    """Missing / malformed / expired token (claims decoded for display only, the API verifies it)."""
    if not token:
        return "No token: the API will answer 401."
    try:
        payload = token.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
    except (IndexError, ValueError, KeyError, TypeError):
        return "This doesn't look like a Keycloak token."
    left = int(exp - time.time())
    return f"Token expired {-left // 60} min ago: get a new one." if left <= 0 else None


with st.sidebar:
    if _problem := _token_problem(_token):
        st.warning(_problem)


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _get(path: str, timeout: int = 5):
    r = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict):
    r = requests.post(f"{API_BASE}{path}", json=payload, headers=HEADERS, timeout=5)
    r.raise_for_status()
    return r.json()


def _patch(path: str, payload: dict):
    r = requests.patch(f"{API_BASE}{path}", json=payload, headers=HEADERS, timeout=5)
    r.raise_for_status()
    return r.json()


def _delete(path: str):
    r = requests.delete(f"{API_BASE}{path}", headers=HEADERS, timeout=5)
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
    # /api/v1 needs no token, so this only tests that the server is up
    requests.get(f"{API_BASE}/api/v1", timeout=2)
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


def _render_keyword_tags(kws: list[dict]) -> None:
    """
    Keywords as tags. When they carry a "weight" (from GET /user/{id}/keywords), the
    weight is shown and the tag fades as it decays; expired ones are struck through.
    """
    def tag(k: dict) -> str:
        weight = k.get("weight")
        label = k["value"] if weight is None else f'{k["value"]} · {weight:.2f}'
        opacity = 1.0 if weight is None else max(0.35, weight)
        strike = "text-decoration:line-through;" if k.get("expired") else ""
        return (f'<span style="background:#e8f4f8; border:1px solid #aecfe0; border-radius:14px; '
                f'padding:3px 12px; margin:3px; display:inline-block; font-size:0.9rem; '
                f'opacity:{opacity}; {strike}">{label}</span>')

    st.markdown(" ".join(tag(k) for k in kws), unsafe_allow_html=True)


def _weighted_keywords(user_id: str) -> list[dict] | None:
    """Keywords with weights, or None on API versions without the endpoint."""
    try:
        return _get(f"/user/{user_id}/keywords")["keywords"]
    except Exception:
        return None



# ---------------------------------------------------------------------------
# DMM id user
# ---------------------------------------------------------------------------


# DMM users shown in the dropdown: "Name Surname" -> user ID in the DMM
_DMM_USERS = {
    "Luca Agostini": "38894023-1b01-4646-a2f8-7fbab0f05d99",
    "Niccolò Marastoni": "ee01595a-ceec-4f54-8ece-f5e967f6036e",
}


def _add_dmm_user():
    with st.expander("Add a DMM user to the local graph"):
        who = st.selectbox("DMM user", [*_DMM_USERS, "Other…"])
        uid = st.text_input("User ID").strip() if who == "Other…" else _DMM_USERS[who]
        label = f"DMM {uid[:8]}" if who == "Other…" else who
        name, _, surname = label.partition(" ")
        st.caption(f"{label}  ·  {uid}")
        if uid and st.button("Add user"):
            payload = {"name": name, "surname": surname or "-",
                       "email": "dmm@example.org", "affiliation": "DMM"}
            try:
                _post(f"/user/{uid}", payload)
                st.rerun()
            except requests.HTTPError as e:
                st.error(e.response.json().get("detail", e))
            except Exception as e:
                st.error(f"Could not add user: {e}")



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

    if DMM_MODE:
        _add_dmm_user()

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
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            st.warning(e.response.json()["detail"])
        else:
            st.error(f"Could not load user: {e}")
        return
    except Exception as e:
        st.error(f"Could not load user: {e}")
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
        weighted = _weighted_keywords(user_id)
        session_weighted = [k for k in weighted or [] if k["source"] == "session"]
        if session_weighted:
            _render_keyword_tags(session_weighted)
            st.caption("Weight halves every 30 days (by default) since the keyword was last extracted. "
                       "Struck-through keywords have expired: they are no longer sent to other services, "
                       "until they are extracted again.")
        else:
            _render_keyword_tags(kws)
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
    if all_queries or DMM_MODE:
        st.divider()
        st.subheader("Generate keywords from sessions")
        
        if DMM_MODE:
            with st.expander("Queries in DMM"):
                try:
                    st.json(_get(f"/user/{user_id}/queries_test", timeout=30))
                except Exception as e:
                    st.error(f"Could not load DMM queries: {e}")

        if st.button("Generate", key="btn_gen_kw"):
            st.session_state._gen_kw_user = user_id
            st.session_state.pop("_gen_kw_result", None)
            st.session_state.pop("_gen_kw_all_extracted", None)
            unextracted = [
                s for s in user.get("sessions", [])
                if not s.get("extracted") and s.get("queries")
            ]
            if not unextracted and not DMM_MODE:
                st.session_state._gen_kw_all_extracted = True
            else:
                try:
                    resp = _get(f"/user/{user_id}/generate-keywords", timeout=130)
                    st.session_state._gen_kw_result = resp["keywords"]
                except requests.HTTPError as e:
                    st.error(f"Could not generate keywords: {e.response.json().get('detail', e)}")
                except Exception as e:
                    st.error(f"Could not generate keywords: {e}")

        if st.session_state.get("_gen_kw_user") == user_id:
            if st.session_state.get("_gen_kw_all_extracted"):
                st.info("All session keywords have already been extracted.")
            raw_kw = st.session_state.get("_gen_kw_result")
            if raw_kw == []:
                st.info("The LLM found no keywords in these sessions.")
            if raw_kw:
                # Older API versions return the raw LLM text instead of a list
                keywords = _parse_llm_keywords(raw_kw) if isinstance(raw_kw, str) else raw_kw
                existing = {k["value"].lower() for k in user.get("keywords", [])}
                st.write("**Generated keywords:**")
                for kw in keywords:
                    note = "already saved: its weight will be refreshed" if kw.lower() in existing else "**new**"
                    st.write(f"- {kw} ({note})")

                if st.button("Accept & save", key="btn_accept_kw", type="primary"):
                    sessions = user.get("sessions", [])
                    for s in sessions:
                        if not s.get("extracted") and s.get("queries"):
                            s["extracted"] = True
                    try:
                        try:
                            # Appends new keywords and refreshes the ones already saved
                            res = _post(f"/user/{user_id}/keywords", {"keywords": keywords})
                            _patch(f"/user/{user_id}", {"sessions": sessions})
                            msg = f"{len(res['added'])} new keyword(s) added, {len(res['refreshed'])} refreshed."
                        except requests.HTTPError as e:
                            if e.response.status_code not in (404, 405):
                                raise
                            # Older API without the append endpoint: merge here instead of overwriting
                            merged = user.get("keywords", []) + [
                                {"value": kw} for kw in keywords if kw.lower() not in existing]
                            _patch(f"/user/{user_id}", {"keywords": merged, "sessions": sessions})
                            msg = "Keywords appended (older API: no timestamps)."
                        st.session_state.pop("_gen_kw_result", None)
                        st.session_state._gen_kw_saved = msg + " Sessions marked as extracted."
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save keywords: {e}")

            if saved := st.session_state.pop("_gen_kw_saved", None):
                st.success(saved)


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
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            st.warning(e.response.json()["detail"])
        else:
            st.error(f"Could not load user: {e}")
        return
    except Exception as e:
        st.error(f"Could not load user: {e}")
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

    session_kws = user.get("keywords", [])
    orcid_kws = (user.get("orcid") or {}).get("keywords", [])
    if session_kws:
        st.markdown("**Session keywords**")
        _render_keyword_tags(session_kws)
    if orcid_kws:
        st.markdown("**ORCID keywords**")
        _render_keyword_tags(orcid_kws)

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
# DMM queries page
# ---------------------------------------------------------------------------

# Called directly (not through the profiler API) for the recent-queries view, like Luca's curl
DMM_URL = os.getenv("DMM_URL", "https://datagems-dev.scayle.es/dmm").rstrip("/")


def _recent_dmm_queries(n: int) -> list[dict]:
    """The n most recent NLQ/CDD queries by any user, newest first, straight from the DMM."""
    # The DMM doesn't sort by time, so fetch a large page and sort here
    r = requests.get(
        f"{DMM_URL}/api/v1/aplog/search",
        params={"operator": ["NLQ_Operator", "CDD_Operator"], "limit": 1000},
        headers=HEADERS,
        timeout=60,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()

    rows = []
    for log in r.json()["aplogs"]:
        nodes = log["ap"]["nodes"]
        ap = next((x for x in nodes if "Analytical_Pattern" in x["labels"]), {})
        user = next((x for x in nodes if "User" in x["labels"]), {})
        for node in nodes:
            props = node.get("properties", {})
            # Same rule as extract_queries in the API: SQL operators also carry a "query" property
            if "Operator" in node["labels"] and "SQL_Operator" not in node["labels"] and props.get("query"):
                rows.append({
                    "timestamp": props.get("startTime") or ap.get("properties", {}).get("startTime"),
                    "user_id": user.get("id"),
                    "query": " ".join(str(props["query"]).split()),
                })
    rows.sort(key=lambda row: str(row["timestamp"]), reverse=True)
    return rows[:n]


def page_dmm_queries():
    st.title("DMM queries")
    _dmm_user_queries()
    st.divider()
    _dmm_recent_queries()


def _dmm_recent_queries():
    st.subheader("Most recent queries by any user")
    st.caption(f"Read directly from the DMM ({DMM_URL}) with the sidebar token. "
               "Useful to find which user ID a query you just sent was logged under.")

    with st.form("dmm_recent_form"):
        n = st.number_input("Number of queries", min_value=1, max_value=500, value=10, step=5)
        submitted = st.form_submit_button("Show recent queries")
    if not submitted:
        return

    try:
        with st.spinner("Asking the DMM..."):
            rows = _recent_dmm_queries(int(n))
    except requests.HTTPError as e:
        st.error(f"The DMM returned {e.response.status_code}: {e.response.text[:200]}")
        return
    except Exception as e:
        st.error(f"Could not reach the DMM: {e}")
        return

    if not rows:
        st.info("The DMM has no NLQ/CDD queries.")
        return
    st.dataframe(rows, hide_index=True, width="stretch")


def _dmm_user_queries():
    st.subheader("Queries of one user")
    st.caption("Queries the DMM has logged for a user ID (NLQ and CDD operators), via this API's "
               "queries_test endpoint. The token needs the DMM audience as well as this API's.")

    with st.form("dmm_queries_form"):
        uid = st.text_input("User ID", placeholder="ee01595a-ceec-4f54-8ece-f5e967f6036e").strip()
        submitted = st.form_submit_button("Get queries")
    if not submitted or not uid:
        return

    try:
        if str(uuid.UUID(uid)) != uid:
            raise ValueError
    except ValueError:
        st.error("The user ID must be a lowercase, hyphenated UUID.")
        return

    try:
        with st.spinner("Asking the DMM..."):
            data = _get(f"/user/{uid}/queries_test", timeout=30)
    except requests.HTTPError as e:
        st.error(f"{e.response.status_code}: {e.response.json().get('detail', e)}")
        return
    except Exception as e:
        st.error(f"Could not load queries: {e}")
        return

    queries = data.get("queries", {})
    if not queries:
        st.info("The DMM has no queries for this user ID.")
        return
    st.markdown(f"**{data['count']} queries**")
    st.dataframe(
        [{"timestamp": ts, "query": q} for ts, q in sorted(queries.items(), key=lambda kv: str(kv[0]), reverse=True)],
        hide_index=True,
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Top-level tabs
# ---------------------------------------------------------------------------

tab_users, tab_chat, tab_dmm = st.tabs(["Users", "Chat", "DMM queries"])

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

with tab_dmm:
    page_dmm_queries()
