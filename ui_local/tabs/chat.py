"""
Chat tab: 
    - simulates a user typing queries
    - stored as sessions in grafeo

--> A session is closed after INACTIVITY_MINUTES without queries
"""
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st

from ui_local import client as api
from ui_local.components import render_keyword_tags

INACTIVITY_MINUTES = 5


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
        api.patch(f"/user/{user_id}", {"sessions": sessions})
        return True
    return False


def _active_session(sessions: list) -> dict | None:
    """Most recent open session (no endTime)."""
    return next((s for s in reversed(sessions) if not s.get("endTime")), None)


def render():
    st.title("Chat")

    try:
        users = api.get("/users")["users"]
    except Exception as e:
        st.error(f"Could not load users: {e}")
        return
    if not users:
        st.info("No users yet. Create one in the **Users** tab.")
        return

    idx = st.selectbox("Select user", range(len(users)),
                       format_func=lambda i: f"{users[i]['name']} {users[i]['surname']}",
                       key="chat_user_select")
    user_id = users[idx]["userId"]

    try:
        user = api.get(f"/user/{user_id}")
    except Exception as e:
        st.error(f"Could not load user profile: {e}")
        return

    if session_kws := user.get("keywords", []):
        st.markdown("**Session keywords**")
        render_keyword_tags(session_kws)
    if orcid_kws := (user.get("orcid") or {}).get("keywords", []):
        st.markdown("**ORCID keywords**")
        render_keyword_tags(orcid_kws)

    sessions = user.get("sessions", [])
    active = _active_session(sessions)
    if active and _close_if_inactive(user_id, active, sessions):
        active = None

    st.divider()
    if active:
        st.caption(f"Session `{active['sessionId'][:8]}...`  started {active['startTime']}")
        for q in active.get("queries", []):
            with st.chat_message("user"):
                st.write(q["text"])
                if q.get("typedAt"):
                    st.caption(q["typedAt"])
    else:
        st.caption("No active session yet. Send a message to start one.")

    if prompt := st.chat_input("Type a message..."):
        now = datetime.now(timezone.utc).isoformat()
        new_query = {"text": prompt, "typedAt": now}

        # Re-fetch to avoid overwriting concurrent changes
        sessions = api.get(f"/user/{user_id}").get("sessions", [])
        if active := _active_session(sessions):
            active.setdefault("queries", []).append(new_query)
        else:
            sessions.append({"sessionId": str(uuid.uuid4()), "startTime": now, "queries": [new_query]})

        try:
            api.patch(f"/user/{user_id}", {"sessions": sessions})
        except Exception as e:
            st.error(f"Could not save message: {e}")
        st.rerun()
