"""
Widgets and parsers shared by more than one tab.
"""
import ast
import re
from datetime import date, datetime

import streamlit as st

from ui_local import client as api


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_llm_keywords(text: str) -> list[str]:
    """Parses LLM keyword output — handles Python list literals and comma/newline lists."""
    try:
        parsed = ast.literal_eval(text.strip())
        if isinstance(parsed, list):
            return [str(k).strip() for k in parsed if str(k).strip()]
    except (ValueError, SyntaxError):
        pass
    cleaned = (re.sub(r"^[\s\-\*\•\d\.]+", "", p).strip() for p in re.split(r"[\n,]+", text))
    return [p for p in cleaned if p]


def parse_orcid_raw(raw: dict, orcid_id: str) -> dict:
    """Raw ORCID record -> the API's ORCID model (id, keywords, publications)."""
    kw_list = (raw.get("person") or {}).get("keywords", {}).get("keyword", [])
    keywords = [{"value": k["content"]} for k in kw_list if k.get("content")]

    pubs = []
    groups = (raw.get("activities-summary") or {}).get("works", {}).get("group", [])
    for group in groups:
        for summary in group.get("work-summary", []):
            title = (summary.get("title") or {}).get("title", {}).get("value", "")
            jt = summary.get("journal-title")
            yr = (summary.get("publication-date") or {}).get("year")
            doi = next((e.get("external-id-value", "")
                        for e in (summary.get("external-ids") or {}).get("external-id", [])
                        if e.get("external-id-type") == "doi"), "")
            if title:
                pubs.append({
                    "title": title, "doi": doi,
                    "journal": jt.get("value", "") if jt else "",
                    "year": int(yr["value"]) if yr and yr.get("value") else 0,
                    "authors": [],
                })

    return {"id": orcid_id, "keywords": keywords, "publications": pubs}


# ---------------------------------------------------------------------------
# Keyword tags
# ---------------------------------------------------------------------------

def render_keyword_tags(kws: list[dict]) -> None:
    """
    Keywords as tags. When they carry a "weight" (from GET /user/{id}/keywords), the
    weight is shown and the tag fades as it decays; expired ones are struck through.
    """
    def tag(k: dict) -> str:
        weight = k.get("weight")
        label = k["value"] if weight is None else f'{k["value"]} · {weight:.2f}'
        opacity = 1.0 if weight is None else max(0.35, weight)
        strike = "text-decoration:line-through;" if k.get("expired") else ""
        return (f'<span style="background:#e8f4f8; color:#1a3a4a; border:1px solid #aecfe0; border-radius:14px; '
                f'padding:3px 12px; margin:3px; display:inline-block; font-size:0.9rem; '
                f'opacity:{opacity}; {strike}">{label}</span>')

    st.markdown(" ".join(tag(k) for k in kws), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# User form (Create and Edit pages)
# ---------------------------------------------------------------------------

def render_user_form(defaults: dict = None) -> dict | None:
    """
    Renders all editable user fields. Returns the payload dict when the form
    is submitted, or None while the user is still filling it in.
    """
    d = defaults or {}
    d_orc = d.get("orcid") or {}
    d_loc = d.get("location") or {}

    dob_default = None
    if d.get("dateOfBirth"):
        try:
            dob_default = datetime.fromisoformat(str(d["dateOfBirth"])).date()
        except (ValueError, TypeError):
            pass

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name *", value=d.get("name", ""))
        dob = st.date_input("Date of birth", value=dob_default,
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
            city = lc1.text_input("City", value=d_loc.get("city", ""))
            country = lc2.text_input("Country", value=d_loc.get("country", ""))

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
                        st.session_state._orcid_data = parse_orcid_raw(api.get(f"/orcid/{orcid_id}"), orcid_id)
                        st.success("ORCID data fetched.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not fetch ORCID data: {e}")
                else:
                    st.warning("Enter an ORCID ID first.")

            if fetched := st.session_state.get("_orcid_data"):
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
    if not st.button("Save", type="primary"):
        return None
    if not all([name, surname, email, affiliation]):
        st.warning("Please fill in all required fields (marked with *).")
        return None

    payload: dict = {"name": name, "surname": surname, "email": email, "affiliation": affiliation}
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
