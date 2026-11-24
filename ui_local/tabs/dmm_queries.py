"""
DMM queries tab: the queries of one user (via the API's queries_test endpoint)
and the most recent queries by any user (read straight from the DMM).
"""
import os
import uuid

import requests
import streamlit as st

from ui_local import client as api

# Called directly (not through the profiler API) for the recent-queries view
DMM_URL = os.getenv("DMM_URL", "https://datagems-dev.scayle.es/dmm").rstrip("/")


def render():
    st.title("DMM queries")
    _user_queries()
    st.divider()
    _recent_queries()


def _recent_dmm_queries(n: int) -> list[dict]:
    '''
    The n most recent NLQ/CDD queries by any user, newest first, straight from the DMM
    '''
    # The DMM doesn't sort by time, so fetch a large page and sort here
    r = requests.get(
        f"{DMM_URL}/api/v1/aplog/search",
        params={"operator": ["NLQ_Operator", "CDD_Operator"], "limit": 1000},
        headers=api.headers(),
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


def _recent_queries():
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


def _user_queries():
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
            data = api.get(f"/user/{uid}/queries_test", timeout=30)
    except requests.HTTPError as e:
        st.error(api.error_detail(e))
        return
    except Exception as e:
        st.error(f"Could not load queries: {e}")
        return

    queries = data.get("queries", [])
    if not queries:
        st.info("The DMM has no queries for this user ID.")
        return
    st.markdown(f"**{data['count']} queries**")
    st.dataframe(
        [{"timestamp": q["typedAt"], "query": q["text"]} for q in reversed(queries)],
        hide_index=True,
        width="stretch",
    )
