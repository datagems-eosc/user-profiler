import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="User Profiler", layout="wide")


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _get(path: str):
    r = requests.get(f"{API_BASE}{path}", timeout=5)
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
        if key.startswith("_pub_count") or key.startswith("_sess_count"):
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
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name *", value=d.get("name", ""))
        age = st.number_input("Age *", min_value=0, max_value=150,
                              value=int(d.get("age", 0)))
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
            orcid_id = st.text_input("ORCID ID", value=d_orc.get("id", ""))

            kw_default = "\n".join(k["value"] for k in d_orc.get("keywords", []))
            kw_raw = st.text_area("Keywords (one per line)", value=kw_default)

            st.write("**Publications**")
            if "_pub_count" not in st.session_state:
                st.session_state._pub_count = max(1, len(d_orc.get("publications", [])))

            existing_pubs = d_orc.get("publications", [])
            pub_data = []
            for i in range(st.session_state._pub_count):
                ep = existing_pubs[i] if i < len(existing_pubs) else {}
                with st.container(border=True):
                    st.caption(f"Publication {i + 1}")
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        p_title = st.text_input("Title", value=ep.get("title", ""),
                                                key=f"pub_{i}_title")
                        p_doi = st.text_input("DOI", value=ep.get("doi", ""),
                                              key=f"pub_{i}_doi")
                    with pc2:
                        p_journal = st.text_input("Journal", value=ep.get("journal", ""),
                                                  key=f"pub_{i}_journal")
                        p_year = st.number_input("Year", min_value=1900, max_value=2100,
                                                 value=int(ep.get("year", 2024)),
                                                 key=f"pub_{i}_year")
                    author_default = ", ".join(
                        a["fullName"] for a in ep.get("authors", [])
                    )
                    p_authors = st.text_input(
                        "Authors (comma-separated)", value=author_default,
                        key=f"pub_{i}_authors"
                    )
                    pub_data.append({
                        "title": p_title, "doi": p_doi,
                        "journal": p_journal, "year": int(p_year),
                        "authors": [
                            {"fullName": n.strip()}
                            for n in p_authors.split(",") if n.strip()
                        ],
                    })

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("+ Add publication"):
                    st.session_state._pub_count += 1
                    st.rerun()
            with bc2:
                if st.button("- Remove last") and st.session_state._pub_count > 1:
                    st.session_state._pub_count -= 1
                    st.rerun()

    st.divider()

    # -- Submit --
    if st.button("Save", type="primary"):
        if not all([name, surname, email, affiliation, age]):
            st.warning("Please fill in all required fields (marked with *).")
            return None

        payload: dict = {
            "name": name, "surname": surname, "age": int(age),
            "email": email, "affiliation": affiliation,
        }

        if add_loc and city and country:
            payload["location"] = {"city": city, "country": country}

        if add_orc and orcid_id:
            payload["orcid"] = {
                "id": orcid_id,
                "keywords": [
                    {"value": k.strip()} for k in kw_raw.splitlines() if k.strip()
                ],
                "publications": [
                    p for p in pub_data if p["title"] and p["doi"]
                ],
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
    c1.metric("Age", user["age"])
    c2.metric("Email", user["email"])
    c3.metric("Affiliation", user["affiliation"])

    # Location
    if user.get("location"):
        st.subheader("Location")
        loc = user["location"]
        st.write(f"{loc['city']}, {loc['country']}")

    # ORCID
    if user.get("orcid"):
        st.subheader("ORCID")
        orc = user["orcid"]
        st.write(f"**ID:** {orc['id']}")

        if orc.get("keywords"):
            st.write("**Keywords:** " + " · ".join(k["value"] for k in orc["keywords"]))

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
            label = f"{s['sessionId']}  —  {s['startTime']}"
            with st.expander(label):
                if s.get("endTime"):
                    st.write(f"**End:** {s['endTime']}")
                if s.get("queries"):
                    for q in s["queries"]:
                        ts = f"  `{q['typedAt']}`" if q.get("typedAt") else ""
                        st.write(f"- {q['text']}{ts}")


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
# Router
# ---------------------------------------------------------------------------

page = st.session_state.page

if page == "list":
    page_list()
elif page == "view":
    page_view()
elif page == "create":
    page_create()
elif page == "edit":
    page_edit()
