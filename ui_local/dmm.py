"""
DMM widgets used inside the Users tab (user view and list): the user's DMM queries,
the keyword refresh status and, in "Local + DMM" mode, the 10-second live refresh.
"""
from datetime import datetime

import requests
import streamlit as st

from ui_local import client as api

# DMM users shown in the dropdown: "Name Surname" -> user ID in the DMM
DMM_USERS = {
    "Luca Agostini": "38894023-1b01-4646-a2f8-7fbab0f05d99",
    "Niccolò Marastoni": "ee01595a-ceec-4f54-8ece-f5e967f6036e",
}

_KW_ICONS = {"ok": "🟢", "error": "🔴", "skipped": "⚪"}


def add_dmm_user():
    with st.expander("Add a DMM user to the local graph"):
        who = st.selectbox("DMM user", [*DMM_USERS, "Other…"])
        uid = st.text_input("User ID").strip() if who == "Other…" else DMM_USERS[who]
        label = f"DMM {uid[:8]}" if who == "Other…" else who
        name, _, surname = label.partition(" ")
        st.caption(f"{label}  ·  {uid}")
        if uid and st.button("Add user"):
            payload = {"name": name, "surname": surname or "-",
                       "email": "dmm@example.org", "affiliation": "DMM"}
            try:
                api.post(f"/user/{uid}", payload)
                st.rerun()
            except requests.HTTPError as e:
                st.error(api.error_detail(e))
            except Exception as e:
                st.error(f"Could not add user: {e}")


def saved_query_times(user: dict) -> set:
    '''
    typedAt of the queries already saved in grafeo, parsed so "...Z" and "...+00:00" compare equal
    '''
    times = set()
    for s in user.get("sessions", []):
        for q in s.get("queries", []):
            try:
                times.add(datetime.fromisoformat(str(q["typedAt"])))
            except (KeyError, ValueError):
                pass
    return times


def render_dmm_queries(user_id: str, saved: set = frozenset()) -> list[dict]:
    '''
    Show the queries the DMM has under this user ID and return them ([{text, typedAt}], empty on error)
    '''
    cache = st.session_state.setdefault("_dmm_queries_cache", {})
    key = (api.api_base(), user_id)

    st.divider()
    head, refresh = st.columns([5, 1])
    head.subheader("Queries in DMM")
    if refresh.button("Refresh", key=f"btn_dmm_refresh_{user_id}"):
        cache.pop(key, None)

    if key not in cache:
        try:
            with st.spinner("Asking the DMM..."):
                cache[key] = {"queries": api.get(f"/user/{user_id}/queries_test", timeout=30).get("queries", [])}
        except requests.HTTPError as e:
            # Not cached, so the next rerun tries again (e.g. after pasting a token with the DMM audience)
            st.error(f"Could not load DMM queries ({api.error_detail(e)})")
            return []
        except Exception as e:
            st.error(f"Could not load DMM queries: {e}")
            return []

    queries = cache[key]["queries"]
    if not queries:
        st.info("The DMM has no queries under this user ID.")
    else:
        st.caption(f"{len(queries)} queries, newest first")
        st.dataframe(
            [{"saved": datetime.fromisoformat(q["typedAt"]) in saved,
              "timestamp": q["typedAt"], "query": q["text"]}
             for q in sorted(queries, key=lambda q: q["typedAt"], reverse=True)],
            column_config={"saved": st.column_config.CheckboxColumn("In grafeo")},
            hide_index=True,
            width="stretch",
        )
    return queries


# ---------------------------------------------------------------------------
# Automatic keyword refresh (dev endpoint refresh-keyword_test)
# ---------------------------------------------------------------------------

def refresh_keywords(user_id: str) -> None:
    '''
    Turns the user's new DMM queries into keywords; the outcome is shown by render_refresh_status
    '''
    state = {"user_id": user_id, "result": None, "error": None}
    try:
        with st.spinner("Refreshing keywords from new DMM queries..."):
            state["result"] = api.post(f"/user/{user_id}/refresh-keyword_test", timeout=300)
    except requests.HTTPError as e:
        state["error"] = api.error_detail(e)
    except Exception as e:
        state["error"] = str(e)
    st.session_state._kw_refresh = state


def render_refresh_status(user_id: str) -> None:
    state = st.session_state.get("_kw_refresh")
    if not state or state["user_id"] != user_id:
        return
    if state["error"]:
        st.error(f"Keyword refresh failed: {state['error']}")
        return
    s = state["result"]
    dmm, llm = st.columns(2)
    dmm.write(f"{_KW_ICONS[s['dmm']]} DMM: {s['dmm']}")
    llm.write(f"{_KW_ICONS[s['llm']]} LLM: {s['llm']}")
    if s["detail"]:
        st.warning(s["detail"])
    if s["added"] or s["refreshed"]:
        st.caption(f"New: {', '.join(s['added']) or '—'}  |  Refreshed: {', '.join(s['refreshed']) or '—'}")


@st.fragment(run_every="10s")
def live_dmm(user_id: str, saved: set):
    '''
    "Local + DMM" mode only: refresh every 10 s, then show the DMM queries and the outcome
    '''
    if st.session_state.pop("_skip_refresh", False):
        pass  # full rerun just after an update: keep the "ok" status on screen
    else:
        refresh_keywords(user_id)
        if ((st.session_state.get("_kw_refresh") or {}).get("result") or {}).get("llm") == "ok":
            st.session_state._skip_refresh = True
            st.rerun(scope="app")  # reloads user, keywords and the "In grafeo" column
    st.session_state.get("_dmm_queries_cache", {}).pop((api.api_base(), user_id), None)
    render_dmm_queries(user_id, saved)
    render_refresh_status(user_id)
