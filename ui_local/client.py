"""
HTTP client for the User Profiler API, configured from the sidebar widgets
(st.session_state["api_choice"] and st.session_state["token"]).
Read at call time, so every module sees the current sidebar values.
"""
import base64
import json
import time

import requests
import streamlit as st

API_OPTIONS = {
    "Local": "http://localhost:8000",
    "DataGEMS (dev)": "https://datagems-dev.scayle.es/up",
    # Local API, plus the DMM-specific widgets (live refresh, add DMM user)
    "Local + DMM": "http://localhost:8000",
}


# ---------------------------------------------------------------------------
# Sidebar settings
# ---------------------------------------------------------------------------

def api_choice() -> str:
    return st.session_state.get("api_choice", next(iter(API_OPTIONS)))


def api_base() -> str:
    return API_OPTIONS[api_choice()]


def dmm_mode() -> bool:
    return api_choice() == "Local + DMM"


def token() -> str:
    return (st.session_state.get("token") or "").strip().removeprefix("Bearer ").strip()


def headers() -> dict:
    t = token()
    return {"Authorization": f"Bearer {t}"} if t else {}


# ---------------------------------------------------------------------------
# Token helpers (display only: the API verifies the signature)
# ---------------------------------------------------------------------------

def claims(tok: str) -> dict:
    """Token claims, {} if malformed."""
    try:
        payload = tok.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, TypeError):
        return {}


def token_problem(tok: str) -> str | None:
    """Missing / malformed / expired token."""
    if not tok:
        return "No token: the API will answer 401."
    exp = claims(tok).get("exp")
    if exp is None:
        return "This doesn't look like a Keycloak token."
    left = int(exp - time.time())
    return f"Token expired {-left // 60} min ago: get a new one." if left <= 0 else None


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def _call(method: str, path: str, timeout: int = 5, **kwargs):
    r = requests.request(method, f"{api_base()}{path}", headers=headers(), timeout=timeout, **kwargs)
    r.raise_for_status()
    return r.json()


def get(path: str, timeout: int = 5):
    return _call("GET", path, timeout)


def post(path: str, payload: dict | None = None, timeout: int = 5):
    return _call("POST", path, timeout, json=payload)


def patch(path: str, payload: dict):
    return _call("PATCH", path, json=payload)


def delete(path: str):
    return _call("DELETE", path)


def error_detail(e: requests.HTTPError) -> str:
    """'<status>: <detail>' from an API error, whether or not the body is JSON."""
    try:
        detail = e.response.json().get("detail", e.response.text)
    except ValueError:  # non-JSON body (plain-text 500, proxy HTML, empty)
        detail = e.response.text[:300] or e
    return f"{e.response.status_code}: {detail}"
