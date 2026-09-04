def build_interest_profile(profile: dict) -> dict:
    """
    Shape a raw load_user_profile() dict into a portable interest-profile DTO
    meant for consumption by other services on the platform. Merges
    session-extracted and ORCID keywords, and drops PII (email, dateOfBirth)
    and the session/query log, which is local bookkeeping specific to this
    service rather than a stable cross-service contract.
    """
    session_kws = [k["value"] for k in profile.get("keywords", [])]
    orcid = profile.get("orcid")
    orcid_kws = [k["value"] for k in orcid["keywords"]] if orcid else []
    merged_keywords = list(dict.fromkeys(session_kws + orcid_kws))

    return {
        "userId": profile["userId"],
        "keywords": merged_keywords,
        "location": profile.get("location"),
        "affiliation": profile.get("affiliation"),
        "orcid": {"id": orcid["id"]} if orcid else None,
    }
