import os
from datetime import datetime, timezone
from typing import Optional

# A session keyword's weight halves every KEYWORD_HALF_LIFE_DAYS since it was last
# (re-)extracted; below KEYWORD_MIN_WEIGHT it is hidden from the interest profile.
# ORCID keywords have no timestamps and get the constant ORCID_KEYWORD_WEIGHT.
KEYWORD_HALF_LIFE_DAYS = float(os.getenv("KEYWORD_HALF_LIFE_DAYS", "30"))
KEYWORD_MIN_WEIGHT = float(os.getenv("KEYWORD_MIN_WEIGHT", "0.1"))
ORCID_KEYWORD_WEIGHT = float(os.getenv("ORCID_KEYWORD_WEIGHT", "0.5"))


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
