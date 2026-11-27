'''
ORCID public Api client:
    - validation of ORCID iDs (format and check digit)
    - fetching a public record
    - parsing a record into the ORCID model stored in the graph
'''
import re

import httpx
from fastapi import HTTPException

ORCID_PUBLIC_API = "https://pub.orcid.org/v3.0"
ORCID_TIMEOUT_SECONDS = 15

_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def normalize_orcid_id(value: str) -> str:
    '''
    Returns the canonical iD (0000-0002-1825-0097), or raises 422.
    Accepts the iD as is, or as a link (https://orcid.org/0000-...), and a lowercase final x.
    '''
    orcid_id = value.strip()
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if orcid_id.lower().startswith(prefix):
            orcid_id = orcid_id[len(prefix):]
    orcid_id = orcid_id.upper()
    if not _ORCID_RE.match(orcid_id):
        raise HTTPException(status_code=422, detail=f"Not an ORCID iD: '{value}' (expected 0000-0000-0000-0000)")

    # ISO 7064 MOD 11-2 check digit, see https://support.orcid.org/hc/en-us/articles/360006897674
    digits = orcid_id.replace("-", "")
    total = 0
    for d in digits[:-1]:
        total = (total + int(d)) * 2
    check = (12 - total % 11) % 11
    if digits[-1] != ("X" if check == 10 else str(check)):
        raise HTTPException(status_code=422, detail=f"Not a valid ORCID iD: '{value}' (wrong check digit)")
    return orcid_id


async def fetch_orcid_profile(orcid_id: str, endpoint: str = "") -> dict:
    '''
    The raw public record of a (valid) ORCID iD
        - 404 if ORCID does not know it
        - 502 if ORCID cannot be reached or answers with an error
    '''
    orcid_id = normalize_orcid_id(orcid_id)
    url = f"{ORCID_PUBLIC_API}/{orcid_id}/{endpoint}".rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=ORCID_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ORCID could not be reached: {exc}") from exc

    if response.status_code == 200:
        return response.json()
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"ORCID profile not found: '{orcid_id}'")
    raise HTTPException(status_code=502, detail=f"ORCID returned {response.status_code}")


def _value(obj, *path):
    '''Follows path through nested dicts, returning None as soon as a step is missing or null'''
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def orcid_name(raw: dict) -> str | None:
    '''
    The name on the record: the credit name if set, otherwise given names + family name
    '''
    name = _value(raw, "person", "name") or {}
    credit = _value(name, "credit-name", "value")
    if credit:
        return credit
    full = " ".join(p for p in (_value(name, "given-names", "value"), _value(name, "family-name", "value")) if p)
    return full or None


def parse_orcid_record(raw: dict, orcid_id: str) -> dict:
    '''
    Raw ORCID record -> the ORCID model (id, keywords, publications)
        - keywords: the researcher's keywords on the record
        - publications: one per work (ORCID groups the copies of a work coming from different
          sources: only the first, preferred, one is kept)
        - missing DOI, journal or year are null; authors are not in the record summary, so empty
    '''
    keywords, seen = [], set()
    for k in _value(raw, "person", "keywords", "keyword") or []:
        value = (k.get("content") or "").strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            keywords.append({"value": value})

    publications = []
    for group in _value(raw, "activities-summary", "works", "group") or []:
        summaries = group.get("work-summary") or []
        if not summaries:
            continue
        work = summaries[0]
        title = (_value(work, "title", "title", "value") or "").strip()
        if not title:
            continue
        year = _value(work, "publication-date", "year", "value")
        doi = next((e.get("external-id-value") for e in _value(work, "external-ids", "external-id") or []
                    if e.get("external-id-type") == "doi" and e.get("external-id-value")), None)
        publications.append({
            "title": title,
            "doi": doi,
            "journal": _value(work, "journal-title", "value") or None,
            "year": int(year) if year and str(year).isdigit() else None,
            "authors": [],
        })

    return {"id": orcid_id, "keywords": keywords, "publications": publications}
