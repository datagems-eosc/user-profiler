"""
UI demo tab: mock of the DataGEMS "Settings" screen for the UI developers.
Only calls the endpoints made for the UI (/user/me...): the user is the token's sub.
"""
import html

import requests
import streamlit as st

from ui_local import client as api
from ui_local.components import parse_orcid_raw, render_keyword_tags

_KW_STATUS = {
    "pending": "No keywords yet: the UP has started a refresh from the user's DMM queries. "
               "Press **Reload** in a few seconds.",
    "no_keywords": "The user's queries were processed but no keywords came out "
                   "(a new refresh has been started).",
    "no_queries": "The UP has never seen this user.",
}


def _ro(col, label: str, value) -> None:
    '''
    Read-only field, styled like the UI's disabled inputs.
    '''
    col.markdown(
        f'<div style="font-size:0.85rem;opacity:0.65">{html.escape(label)}</div>'
        f'<div style="background:rgba(128,128,128,0.12);border:1px solid rgba(128,128,128,0.35);'
        f'border-radius:999px;padding:6px 14px;margin-bottom:8px">{html.escape(str(value or "—"))}</div>',
        unsafe_allow_html=True,
    )


@st.dialog("Edit profile")
def _edit_me_dialog(me: dict):
    old_orcid = (me.get("orcid") or {}).get("id", "")
    with st.form("demo_edit_me"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name *", me["name"])
        surname = c2.text_input("Surname *", me["surname"])
        email = st.text_input("Email *", me["email"])
        affiliation = st.text_input("Affiliation *", me["affiliation"])
        orcid_id = st.text_input("ORCID iD", old_orcid,
                                 help="Leave empty to remove it. A new iD is fetched from ORCID on save.")
        if not st.form_submit_button("Save", type="primary"):
            return

    fields = {"name": name.strip(), "surname": surname.strip(),
              "email": email.strip(), "affiliation": affiliation.strip()}
    if not all(fields.values()):
        st.warning("Please fill in all required fields (marked with *).")
        return

    # PATCH only what changed
    payload = {k: v for k, v in fields.items() if v != me.get(k)}
    orcid_id = orcid_id.strip()
    if orcid_id != old_orcid:
        if not orcid_id:
            payload["orcid"] = None
        else:
            try:
                with st.spinner("Fetching from ORCID..."):
                    payload["orcid"] = parse_orcid_raw(api.get(f"/orcid/{orcid_id}", timeout=15), orcid_id)
            except requests.HTTPError as e:
                st.error(f"ORCID {api.error_detail(e)}")
                return
            except Exception as e:
                st.error(f"Could not reach ORCID: {e}")
                return
    if not payload:
        st.info("Nothing changed.")
        return

    try:
        api.patch("/user/me", payload)
    except requests.HTTPError as e:
        st.error(f"Could not save: {api.error_detail(e)}")
        return
    except Exception as e:
        st.error(f"Could not save: {e}")
        return
    st.session_state._demo_saved = "Profile updated"
    st.rerun()  # closes the dialog and reloads the profile


@st.dialog("Interest keywords", width="large")
def _keywords_dialog():
    # Runs again on every interaction inside the dialog: always reads the latest keywords from grafeo
    try:
        with st.spinner("Loading keywords..."):
            data = api.get("/user/me/keywords")
    except requests.HTTPError as e:
        st.error(f"Could not load keywords: {api.error_detail(e)}")
        return
    except Exception as e:
        st.error(f"Could not load keywords: {e}")
        return

    if data["status"] == "ok":
        render_keyword_tags(data["keywords"])
        st.caption("Strongest first. The weight halves every 30 days since the keyword was last seen; "
                   "struck-through ones have expired. ORCID keywords have a fixed weight.")
    else:
        st.info(_KW_STATUS.get(data["status"], data["status"]))

    st.button("Reload", key="demo_kw_reload")  # just triggers a rerun, i.e. a new GET


def _load_me() -> dict | None:
    """GET /user/me, or None after showing what went wrong (and a Create button on 404)."""
    try:
        return api.get("/user/me")
    except requests.HTTPError as e:
        if e.response.status_code == 404 and "'me'" in e.response.text:
            # Old API: /user/me falls into /user/{user_id}
            st.error("This API has no `/user/me` endpoints yet: deploy the latest up_api.")
        elif e.response.status_code == 404:
            sub = api.claims(api.token()).get("sub")
            st.info(f"The UP has no profile for `{sub}` yet (it is created at the first query, "
                    "or with `POST /user/me`).")
            if st.button("Create my profile", type="primary"):
                try:
                    api.post("/user/me", {})
                    st.rerun()
                except requests.HTTPError as e2:
                    st.error(f"Could not create the profile: {api.error_detail(e2)}")
        else:
            st.error(f"Could not load the profile: {api.error_detail(e)}")
    except Exception as e:
        st.error(f"Could not load the profile: {e}")
    return None


def render():
    st.title("Settings")
    st.caption("Demo for the DataGEMS UI developers. It only calls the endpoints made for the UI "
               "(`/user/me...`), with the sidebar token: the user is the token's `sub`, "
               "on whichever API is selected in the sidebar.")

    if msg := st.session_state.pop("_demo_saved", None):
        st.toast(msg)

    if not api.claims(api.token()).get("sub"):
        st.info("Paste a valid Keycloak token in the sidebar.")
        return
    if (me := _load_me()) is None:
        return

    # -- Basic info --
    st.subheader("Basic Info")
    st.divider()

    label, content = st.columns([1, 3])
    label.markdown("**User Info**  \nYour account information")
    initials = html.escape((me["name"][:1] + me["surname"][:1]).upper())
    content.markdown(
        f'<div style="display:flex;align-items:center;gap:14px">'
        f'<div style="width:48px;height:48px;border-radius:50%;background:#e2e8f0;color:#334155;'
        f'display:flex;align-items:center;justify-content:center;font-weight:600">{initials}</div>'
        f'<div><b>{html.escape(me["name"])} {html.escape(me["surname"])}</b><br>'
        f'<span style="color:#64748b">{html.escape(me["email"])}</span></div></div>',
        unsafe_allow_html=True,
    )
    st.divider()

    label, c1, c2 = st.columns([1, 1.5, 1.5])
    label.markdown("**Account name**  \nYour account information")
    _ro(c1, "Name", me["name"])
    _ro(c2, "Surname", me["surname"])
    st.divider()

    label, c1, c2 = st.columns([1, 1.5, 1.5])
    label.markdown("**Research profile**  \nAffiliation and ORCID")
    _ro(c1, "Affiliation", me["affiliation"])
    orcid = me.get("orcid")
    _ro(c2, "ORCID iD", orcid and orcid["id"])
    if orcid and orcid.get("publications"):
        c2.caption(f"{len(orcid['publications'])} publications imported from ORCID")
    st.divider()

    # -- Actions --
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Edit profile", key="demo_edit_btn", type="primary", use_container_width=True):
        _edit_me_dialog(me)
    if b2.button("Show keywords", key="demo_kw_btn", use_container_width=True):
        _keywords_dialog()
