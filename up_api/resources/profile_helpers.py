import os
from datetime import datetime, timezone
from typing import Optional

# A session keyword's weight halves every KEYWORD_HALF_LIFE_DAYS since it was last
# (re-)extracted; below KEYWORD_MIN_WEIGHT it is hidden from the interest profile.
# ORCID keywords have no timestamps and get the constant ORCID_KEYWORD_WEIGHT.
KEYWORD_HALF_LIFE_DAYS = float(os.getenv("KEYWORD_HALF_LIFE_DAYS", "30"))
KEYWORD_MIN_WEIGHT = float(os.getenv("KEYWORD_MIN_WEIGHT", "0.1"))
ORCID_KEYWORD_WEIGHT = float(os.getenv("ORCID_KEYWORD_WEIGHT", "0.5"))


# FOR THE AUTOMATIC QUERY REFRESH
# importing the DMM query object
from .data_models import DMMQuery
#   fixed sessionId of the per-user Session that stores the queries fetched from the DMM
HISTORY_SESSION_ID = "dmm-history"
#   fixingf the max amount of queries stored
#       keeping only the last 50
#       --> env var so can be changed form the cluster config without redeploying the service
MAX_STORED_QUERIES = int(os.getenv("MAX_STORED_QUERIES", "50"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def keyword_weight(keyword: dict, now: Optional[datetime] = None) -> float:
    """1.0 when just seen, 0.5 after one half-life, 0.25 after two, …"""
    seen = _parse_dt(keyword.get("lastSeenAt") or keyword.get("addedAt"))
    if seen is None:
        return 1.0  # not stamped yet: stamped the next time the profile is saved
    age_days = max(0.0, ((now or _now()) - seen).total_seconds() / 86400)
    return 0.5 ** (age_days / KEYWORD_HALF_LIFE_DAYS)


def stamp_keywords(keywords: list[dict], previous: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """
    Fills in missing timestamps: a keyword that already existed (same value, ignoring
    case) keeps its previous timestamps, anything else is stamped as seen now.
    Used when a whole keyword list is written (create / edit), so saving a profile
    never resets or loses keyword ages.
    """
    now = now or _now()
    old = {k["value"].lower(): k for k in previous}
    stamped = []
    for k in keywords:
        prev = old.get(k["value"].lower(), {})
        added = k.get("addedAt") or prev.get("addedAt") or now
        stamped.append({**k,
                        "addedAt": added,
                        "lastSeenAt": k.get("lastSeenAt") or prev.get("lastSeenAt") or added})
    return stamped


def append_keywords(existing: list[dict], new_values: list[str], now: Optional[datetime] = None) -> tuple[list[dict], list[str]]:
    """
    Merges freshly extracted keywords into the existing ones: values already present
    (ignoring case) get lastSeenAt refreshed, which restores their full weight; the
    others are appended. Returns the merged list and the values that were new.
    """
    now = now or _now()
    merged = [dict(k) for k in existing]
    index = {k["value"].lower(): k for k in merged}
    added = []
    for value in new_values:
        value = value.strip()
        if not value:
            continue
        if value.lower() in index:
            index[value.lower()]["lastSeenAt"] = now
        else:
            kw = {"value": value, "addedAt": now, "lastSeenAt": now}
            merged.append(kw)
            index[value.lower()] = kw
            added.append(value)
    return merged, added


def weighted_keywords(profile: dict, now: Optional[datetime] = None) -> list[dict]:
    """
    All keywords with their weight and source, strongest first, including expired
    ones (flagged "expired": true). A value present both as a session and an ORCID
    keyword keeps the higher weight.
    """
    now = now or _now()
    orcid = profile.get("orcid")
    entries = [{"value": k["value"], "weight": keyword_weight(k, now), "source": "session",
                "lastSeenAt": k.get("lastSeenAt")} for k in profile.get("keywords", [])]
    entries += [{"value": k["value"], "weight": ORCID_KEYWORD_WEIGHT, "source": "orcid", "lastSeenAt": None}
                for k in (orcid["keywords"] if orcid else [])]

    best: dict[str, dict] = {}
    for e in entries:
        key = e["value"].lower()
        if key not in best or e["weight"] > best[key]["weight"]:
            best[key] = e
    ranked = sorted(best.values(), key=lambda e: e["weight"], reverse=True)
    for e in ranked:
        e["weight"] = round(e["weight"], 3)
        e["expired"] = e["weight"] < KEYWORD_MIN_WEIGHT
    return ranked


def build_interest_profile(profile: dict) -> dict:
    """
    Shape a raw load_user_profile() dict into a portable interest-profile DTO
    meant for consumption by other services on the platform. Merges
    session-extracted and ORCID keywords, ranked by weight (recently seen session
    keywords first, decayed ones hidden), and drops PII (email, dateOfBirth)
    and the session/query log, which is local bookkeeping specific to this
    service rather than a stable cross-service contract.
    """
    orcid = profile.get("orcid")
    active = [e for e in weighted_keywords(profile) if not e["expired"]]

    return {
        "userId": profile["userId"],
        # Plain strings, strongest first: consumers that ignore weights still get the priority order
        "keywords": [e["value"] for e in active],
        "weightedKeywords": [{"value": e["value"], "weight": e["weight"], "source": e["source"]} for e in active],
        "location": profile.get("location"),
        "affiliation": profile.get("affiliation"),
        "orcid": {"id": orcid["id"]} if orcid else None,
    }



# ---------------------------------------------------------------------------
# DMM query history (stored in the "dmm-history" session)
# ---------------------------------------------------------------------------

def _history(profile: dict) -> Optional[dict]:
    '''
    Returns the per-user Session that stores the queries fetched from the DMM, or None
    '''
    return next((s for s in profile["sessions"] if s["sessionId"] == HISTORY_SESSION_ID), None)

def last_processed_at(profile: dict) -> Optional[datetime]:
    '''
    Returns the timestamp of the most recent query already saved in the history
    '''
    history = _history(profile)
    return max((_parse_dt(q["typedAt"]) for q in history["queries"]), default=None) if history else None

def remember_queries(profile: dict, new_queries: list[DMMQuery]) -> None:
    '''
    Addes the new queires to the history
        - if the ddm-history does not exist yet, it is created
        - if the ddm-history exists, the new queries are appended to it
        - sort the queries using the timestamp, to keep only the last MAX_STORED_QUERIES queries
    '''
    history = _history(profile)
    if not new_queries:
            return 
    
    # creating the dmm-history session if it does not exist yet
    if history is None:
        history = {"sessionId": HISTORY_SESSION_ID, "extracted": True, "queries": []}
        profile["sessions"].append(history)
        
    # adding the queries to the history
    history["queries"] += [q.model_dump() for q in new_queries]
    
    # sorting the queries 
    history["queries"] = sorted(history["queries"], key=lambda q: _parse_dt(q["typedAt"]))[-MAX_STORED_QUERIES:]
    
    # add the start and end time to the history session
    #   metadata to keeo the session valid and readable
    history["startTime"] = history["queries"][0]["typedAt"]
    history["endTime"] = history["queries"][-1]["typedAt"]
    
    