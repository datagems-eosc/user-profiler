"""
User Profiler test UI: sidebar (API endpoint + token) and one tab per tested feature.
Each tab lives in ui/tabs/<name>.py and exposes render().
"""
import os

import requests
import streamlit as st

from ui_local import client as api
from ui_local.tabs import chat, dmm_queries, ui_demo, users

st.set_page_config(page_title="User Profiler", layout="wide")

with st.sidebar:
    st.markdown("### API endpoint")
    choice = st.radio("API endpoint", list(api.API_OPTIONS), key="api_choice", label_visibility="collapsed")
    st.caption(api.API_OPTIONS[choice])
    st.text_input(
        "Keycloak token",
        value=os.getenv("DATAGEMS_TOKEN", ""),
        key="token",
        type="password",
        help="Sent as `Authorization: Bearer <token>`; it needs `user-profiler` or `query-recommender` "
             "in its audience. Get one from the DataGEMS AAI (Keycloak).",
    )
    if problem := api.token_problem(api.token()):
        st.warning(problem)

# /api/v1 needs no token, so this only tests that the server is up
try:
    requests.get(f"{api.api_base()}/api/v1", timeout=2)
except (requests.ConnectionError, requests.Timeout):
    st.error(
        "Cannot connect to the User Profiler API.  "
        "Make sure the server is running:  \n"
        "```\nuvicorn up_api.main:app --reload\n```"
    )
    st.stop()

# Adding a tab = one module in ui/tabs + one line here
TABS = {"Users": users, "Chat": chat, "DMM queries": dmm_queries, "UI demo": ui_demo}
for tab, module in zip(st.tabs(list(TABS)), TABS.values()):
    with tab:
        module.render()
