'''
User's query history and keywords:
    - retrieval of the queries from the DMM, 
    - automatic keyword
    - refresh when the QR notifies a new quer 
    - and LLM keyword generation.
'''
import asyncio
from collections import defaultdict
import json
import logging
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from ..resources import security
from ..resources.data_models import DMMQuery, QueryEvent
from ..resources.graph_helpers import load_user_profile
from ..resources.LLM_helpers import generate_keywords_from_session
from ..resources.profile_helpers import (
    MAX_STORED_QUERIES,
    append_keywords,
    last_processed_at,
    remember_queries,
    weighted_keywords,
)
from .user import _ensure_user, _require_user, _save

# for auth
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

logger = logging.getLogger(__name__)

router = APIRouter()

# set the attemps and the interval of attemps for the refresh
#   if the notify query is still not in the DMM
#       if the DMM is not reachable, the error is recorded in the logs
#       if after the attemp the refresh carries on
DMM_QUERY_ATTEMPTS = int(os.getenv("DMM_QUERY_ATTEMPTS", "3"))
DMM_QUERY_RETRY_SECONDS = float(os.getenv("DMM_QUERY_RETRY_SECONDS", "2"))

# Data managment model url
DMM_URL = os.getenv("DMM_URL", "https://datagems-dev.scayle.es/dmm").rstrip("/")


# =================================
# Retriving user's query history

# extract user's queries from a json payload
def extract_queries(aplogs: list[dict]) -> list[DMMQuery]:
    '''
    extract the user's natural-language queries from DMM aplog/search results
    
    Returns
        - a list of DMMQuery (text + typedAt in UTC)
            --> queries without a timestamp are skipped
    '''
    queries = []
    for log in aplogs:
        nodes = log["ap"]["nodes"]
        ap = next((n for n in nodes if "Analytical_Pattern" in n["labels"]), {})
        for n in nodes:
            props = n.get("properties", {})
            # SQL operators also carry a "query" property
            if "Operator" in n["labels"] and "SQL_Operator" not in n["labels"] and props.get("query"):
                timestamp = props.get("startTime") or ap.get("properties", {}).get("startTime")
                if timestamp:
                    queries.append(DMMQuery(text=props["query"], typedAt=timestamp))
    return queries

# exectute the http request to DMM
async def fetch_user_queries(token: str, user_id: str) -> list[DMMQuery]:
    '''
    Input:
        - token (str) security token (auth)
        - user_id (str): id of the user of which the queries will be retrived
    '''
    # flag fpr dev (to use local stored data)
    if os.getenv("MOCK_DMM") == "1":
        with open("mock_aplog.json") as f:
            return extract_queries(json.load(f)["aplogs"])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{DMM_URL}/api/v1/aplog/search",
                params={
                    "userId": user_id,
                    "operator": ["NLQ_Operator", "CDD_Operator"],
                    "limit": MAX_STORED_QUERIES,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"The DMM could not be reached: {exc}") from exc

    # 404 -> no logs available
    if r.status_code == 404:
        return []
    # Any other DMM error (e.g. 401/403 if it rejects the forwarded token) is reported as a 502 with its status
    if r.is_error:
        raise HTTPException(status_code=502, detail=f"The DMM returned {r.status_code}: {r.text[:200]}")
    try:
        return extract_queries(r.json()["aplogs"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="The DMM returned an unexpected response") from exc



# =================================
# Automatic keyword refresh


# creating a lock for each user to avoid concurrent refreshes
_refresh_locks = defaultdict(asyncio.Lock)

def _norm(text: str) -> str:
    '''collapses whitespace, so the notified text and the DMM one compare equal'''
    return " ".join(text.split())


async def _fetch_new_queries(user_id: str, token: str, last, query: str | None) -> list[DMMQuery]:
    '''
    Fetches the user's queries from the DMM and keeps only those newer than the last
    processed one.

    Input:
        - user_id (str): id of the user 
        - token (str): bearer token 
        - last (datetime | None): timestamp of the last processed query
        - query (str | None): text of the query notified by the QR

    Returns:
        - list[DMMQuery]: the new queries

    Raises:
        - HTTPException (502): DMM cannot be reached or returns an error
    '''

    # try to fetch 
        #   for DMM_QUERY_ATTEMPTS times, waiting DMM_QUERY_RETRY_SECONDS between each attempt
    for attempt in range(DMM_QUERY_ATTEMPTS):
        fetched = await fetch_user_queries(token, user_id)
        new_queries = [q for q in fetched if not last or q.typedAt > last]
        if query is None or any(_norm(q.text) == _norm(query) for q in new_queries):
            break
        if attempt < DMM_QUERY_ATTEMPTS - 1:
            await asyncio.sleep(DMM_QUERY_RETRY_SECONDS)

    # warning if the notified query is not in the DMM after the attempts
    # or if the notified query has been already processed
    else:
        # if the notified query is not in the DMM
        #   --> so if the for loop never breaks
        if any(_norm(q.text) == _norm(query) for q in fetched):
            logger.info("Refresh of %s: notified query already processed: %r", user_id, query[:80])
        else:
            logger.warning("Refresh of %s: notified query not found in the DMM after %d attempts: %r",
                            user_id, DMM_QUERY_ATTEMPTS, query[:80])
    return new_queries


async def refresh_user_keywords(user_id: str, token: str, query: str | None = None) -> dict:
    '''
    Refreshes the user's keywords from the queries added to the DMM since the last refresh.

    Input:
        - user_id (str): id of the user 
        - token (str): bearer token 
        - query (str | None): text of the query notified by the QR

    Returns:
        - dict with:
            - dmm (str): "ok" | "error"
            - llm (str): "ok" | "error" | "skipped" (skipped == no new queries)
            - detail (str | None): any error message
            - added (list[str]): keywords not in the profile yet
            - refreshed (list[str]): keywords already present

    Raises:
        - HTTPException (404): user does not exist 
    '''
    
    # result initialization
    result = {"dmm": "ok", "llm": "skipped", "detail": None, "added": [], "refreshed": []}


    # checks the last processed query timestamp and fetches the new queries from the DMM
    async with _refresh_locks[user_id]:
        last = last_processed_at(_require_user(user_id))
        try:
            new_queries = await _fetch_new_queries(user_id, token, last, query)
        except HTTPException as exc:
            logger.warning("Keyword refresh of %s: %s", user_id, exc.detail)
            return result | {"dmm": "error", "detail": exc.detail}
        if not new_queries:
            return result

        try:
            keywords = await asyncio.to_thread(generate_keywords_from_session, {}, queries=new_queries)
        except Exception:
            logger.exception("Keyword refresh of %s: unexpected LLM error", user_id)
            keywords = None
        if keywords is None:
            detail = "The LLM could not be reached or returned an invalid response"
            logger.warning("Keyword refresh of %s: %s", user_id, detail)
            return result | {"llm": "error", "detail": detail}

        profile = load_user_profile(user_id)  # può essere cambiato durante la chiamata LLM
        if profile is None:
            return result | {"llm": "ok", "detail": "User deleted during the refresh"}
        profile["keywords"], added = append_keywords(profile["keywords"], keywords)
        remember_queries(profile, new_queries)
        _save(profile)

    return result | {"llm": "ok", "added": added, "refreshed": [k for k in keywords if k not in added]}


# to track the refresh process 
async def _refresh_in_background(user_id: str, token: str, query: str | None) -> None:
    '''
    Runs the refresh after the 202 
        --> logs its outcome
    '''
    try:
        r = await refresh_user_keywords(user_id, token, query)
        logger.info("Refresh of %s: dmm=%s llm=%s added=%s refreshed=%s detail=%s",
                    user_id, r["dmm"], r["llm"], r["added"], r["refreshed"], r["detail"])
    except Exception:
        logger.exception("Refresh of %s failed", user_id)


#=============================
# Keywords of the token's own user

# exposes the user's keywords to the UI
@router.get("/user/me/keywords", summary="Keywords of the token's own user (UI profile page)")
def get_my_keywords(tasks: BackgroundTasks,
                    token: str = Depends(oauth2_scheme),
                    claims: dict = Depends(security.require_app_scope)):
    '''
    Keywords stored in grafeo, with weight and "expired" flag
        - "ok": keywords available
        - "pending": none yet, a refresh from the DMM has been started -> reload later
        - "no_queries": the UP has never seen this user
        - "no_keywords": processed, but no keywords came out
    '''
    user_id = claims["sub"]
    profile = load_user_profile(user_id)
    if profile is None:
        return {"status": "no_queries", "keywords": []}

    keywords = weighted_keywords(profile)
    if keywords:
        return {"status": "ok", "keywords": keywords}

    tasks.add_task(_refresh_in_background, user_id, token, None)
    if last_processed_at(profile) is None:
        status = "pending" 
    else:
        status = "no_keywords"
    return {"status": status, "keywords": []}


#=============================
# Notify a new query

@router.post("/user/{user_id}/queries", status_code=202, summary="Notify that the user has performed a new query (triggers a refresh)")
def notify_query(user_id: str, payload: QueryEvent, tasks: BackgroundTasks,
                 token: str = Depends(oauth2_scheme),
                 claims: dict = Depends(security.require_app_scope)):
    '''
    notify that the user has performed a new query
        --> creates the user if the UP has never seen it, then triggers the refresh
    '''
    created = _ensure_user(user_id, claims)
    logger.info("Query notified for %s: %r", user_id, payload.query[:80])
    tasks.add_task(_refresh_in_background, user_id, token, payload.query)
    return {"status": "accepted", "created": created}


# =================================
# Generating user's kewywords


@router.get("/user/{user_id}/generate-keywords", summary="Generate keywords from user sessions via LLM")
async def get_generated_keywords(user_id: str, token: str = Depends(oauth2_scheme)):
    profile = _require_user(user_id)
    
    # getting user previous queries
    user_queries = await fetch_user_queries(token, user_id)
    
    # generating the keywords
    result = generate_keywords_from_session(profile, queries=user_queries)
    
    if result is None:
        raise HTTPException(status_code=502, detail="The LLM could not be reached or returned an invalid response")
    return {"keywords": result}
