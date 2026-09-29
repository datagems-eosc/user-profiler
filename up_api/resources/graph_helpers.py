from typing import Optional
from datetime import datetime

from grafeo import GrafeoDB

from .data_models import UserProfile

DB_PATH = "./grafeo_data"

db: GrafeoDB = None


def init_db() -> None:
    global db
    db = GrafeoDB(DB_PATH)


# ---------------------------------------------------------------------------
# Low-level GQL utilities
# ---------------------------------------------------------------------------

def _q(val) -> str:
    """Escape a value for safe inline use in a GQL string literal."""
    return str(val).replace("\\", "\\\\").replace("'", "\\'")


def _dt(val) -> Optional[str]:
    if val is None:
        return None
    return val.isoformat() if isinstance(val, datetime) else str(val)


def _props(**kwargs) -> str:
    """Build a GQL property map literal string, omitting None values."""
    parts = []
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, bool):
            parts.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}: {v}")
        else:
            parts.append(f"{k}: '{_q(str(v))}'")
    return "{" + ", ".join(parts) + "}" if parts else "{}"


def _run(query: str) -> None:
    db.execute(query)


def _gql(query: str) -> list:
    return list(db.execute(query))


# ---------------------------------------------------------------------------
# Graph CRUD operations
# ---------------------------------------------------------------------------

def list_users() -> list[dict]:
    """Return userId, name and surname for every User node in the graph."""
    rows = _gql("MATCH (u:User) RETURN u.userId, u.name, u.surname")
    return [
        {"userId": r["u.userId"], "name": r["u.name"], "surname": r["u.surname"]}
        for r in rows
    ]


def build_user_subgraph(profile: UserProfile) -> None:
    """Write the full user subgraph (User + all connected nodes/edges) to grafeo."""
    uid = _q(profile.userId)

    user_p = _props(
        userId=profile.userId, name=profile.name, surname=profile.surname,
        dateOfBirth=_dt(profile.dateOfBirth), email=profile.email, affiliation=profile.affiliation,
    )
    _run(f"INSERT (:User {user_p})")

    for kw in profile.keywords:
        _run(f"MATCH (u:User {{userId: '{uid}'}}) "
             f"INSERT (u)-[:HAS_SESSION_KEYWORD]->(:Keyword "
             f"{_props(value=kw.value, addedAt=_dt(kw.addedAt), lastSeenAt=_dt(kw.lastSeenAt))})")

    if profile.location:
        loc = profile.location
        _run(f"MATCH (u:User {{userId: '{uid}'}}) "
             f"INSERT (u)-[:HAS_LOCATION]->(:Location {_props(city=loc.city, country=loc.country)})")

    if profile.orcid:
        orc = profile.orcid
        oid = _q(orc.id)
        _run(f"MATCH (u:User {{userId: '{uid}'}}) "
             f"INSERT (u)-[:HAS_ORCID]->(:ORCID {_props(id=orc.id)})")

        for kw in orc.keywords:
            _run(f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o:ORCID {{id: '{oid}'}}) "
                 f"INSERT (o)-[:HAS_KEYWORD]->(:Keyword {_props(value=kw.value)})")

        for pub in orc.publications:
            doi = _q(pub.doi)
            _run(f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o:ORCID {{id: '{oid}'}}) "
                 f"INSERT (o)-[:HAS_PUBLICATION]->(:Publication {_props(title=pub.title, doi=pub.doi, journal=pub.journal, year=pub.year)})")

            for author in pub.authors:
                _run(f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o:ORCID {{id: '{oid}'}})"
                     f"-[:HAS_PUBLICATION]->(p:Publication {{doi: '{doi}'}}) "
                     f"INSERT (p)-[:HAS_AUTHOR]->(:Author {_props(fullName=author.fullName)})")

    for session in profile.sessions:
        sid = _q(session.sessionId)
        extracted = session.extracted if session.extracted else None
        _run(f"MATCH (u:User {{userId: '{uid}'}}) "
             f"INSERT (u)-[:HAS_SESSION]->(:Session {_props(sessionId=session.sessionId, startTime=_dt(session.startTime), endTime=_dt(session.endTime), extracted=extracted)})")

        for query in session.queries:
            _run(f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_SESSION]->(s:Session {{sessionId: '{sid}'}}) "
                 f"INSERT (s)-[:HAS_QUERY]->(:Query {_props(text=query.text, typedAt=_dt(query.typedAt))})")


def delete_user_subgraph(user_id: str) -> None:
    """Remove the user and every node reachable from it (leaf-first)."""
    uid = _q(user_id)
    # Each statement only runs if the MATCH finds real nodes, so nulls never reach DELETE.
    for stmt in [
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_SESSION]->()-[:HAS_QUERY]->(q) DETACH DELETE q",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_SESSION_KEYWORD]->(k) DETACH DELETE k",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_SESSION]->(s) DETACH DELETE s",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_ORCID]->()-[:HAS_PUBLICATION]->()-[:HAS_AUTHOR]->(a) DETACH DELETE a",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_ORCID]->()-[:HAS_PUBLICATION]->(p) DETACH DELETE p",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_ORCID]->()-[:HAS_KEYWORD]->(k) DETACH DELETE k",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o) DETACH DELETE o",
        f"MATCH (:User {{userId: '{uid}'}})-[:HAS_LOCATION]->(l) DETACH DELETE l",
        f"MATCH (u:User {{userId: '{uid}'}}) DETACH DELETE u",
    ]:
        _run(stmt)


def load_user_profile(user_id: str) -> Optional[dict]:
    """Reconstruct a full UserProfile dict by traversing the graph."""
    uid = _q(user_id)

    rows = _gql(
        f"MATCH (u:User {{userId: '{uid}'}}) "
        f"RETURN u.userId, u.name, u.surname, u.dateOfBirth, u.email, u.affiliation"
    )
    if not rows:
        return None

    r = rows[0]
    profile: dict = {
        "userId":      r["u.userId"],
        "name":        r["u.name"],
        "surname":     r["u.surname"],
        "dateOfBirth": r.get("u.dateOfBirth"),
        "email":       r["u.email"],
        "affiliation": r["u.affiliation"],
        "keywords": [], "location": None, "orcid": None, "sessions": [],
    }

    user_kws = _gql(
        f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_SESSION_KEYWORD]->(k) RETURN k.value, k.addedAt, k.lastSeenAt"
    )
    profile["keywords"] = [
        {"value": k["k.value"], "addedAt": k.get("k.addedAt"), "lastSeenAt": k.get("k.lastSeenAt")}
        for k in user_kws
    ]

    loc = _gql(
        f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_LOCATION]->(l) "
        f"RETURN l.city, l.country"
    )
    if loc:
        profile["location"] = {"city": loc[0]["l.city"], "country": loc[0]["l.country"]}

    orc = _gql(
        f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o) RETURN o.id"
    )
    if orc:
        orcid_id = orc[0]["o.id"]
        oid = _q(orcid_id)

        kws = _gql(
            f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o)"
            f"-[:HAS_KEYWORD]->(k) RETURN k.value"
        )

        pubs_rows = _gql(
            f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o)"
            f"-[:HAS_PUBLICATION]->(p) RETURN p.title, p.doi, p.journal, p.year"
        )

        publications = []
        for pr in pubs_rows:
            pdoi = _q(pr["p.doi"])
            authors = _gql(
                f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_ORCID]->(o)"
                f"-[:HAS_PUBLICATION]->(p:Publication {{doi: '{pdoi}'}})"
                f"-[:HAS_AUTHOR]->(a) RETURN a.fullName"
            )
            publications.append({
                "title":   pr["p.title"],
                "doi":     pr["p.doi"],
                "journal": pr["p.journal"],
                "year":    pr["p.year"],
                "authors": [{"fullName": a["a.fullName"]} for a in authors],
            })

        profile["orcid"] = {
            "id":           orcid_id,
            "keywords":     [{"value": k["k.value"]} for k in kws],
            "publications": publications,
        }

    sess_rows = _gql(
        f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_SESSION]->(s) "
        f"RETURN s.sessionId, s.startTime, s.endTime, s.extracted"
    )
    sessions = []
    for sr in sess_rows:
        sid = _q(sr["s.sessionId"])
        queries = _gql(
            f"MATCH (u:User {{userId: '{uid}'}})-[:HAS_SESSION]->(s:Session {{sessionId: '{sid}'}})"
            f"-[:HAS_QUERY]->(q) RETURN q.text, q.typedAt"
        )
        sessions.append({
            "sessionId": sr["s.sessionId"],
            "startTime": sr["s.startTime"],
            "endTime":   sr["s.endTime"],
            "extracted": bool(sr.get("s.extracted")) or False,
            "queries":   [{"text": q["q.text"], "typedAt": q["q.typedAt"]} for q in queries],
        })
    profile["sessions"] = sessions

    return profile
