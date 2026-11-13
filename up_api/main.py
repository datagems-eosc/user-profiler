from contextlib import asynccontextmanager
import os
import uuid

import asyncio
from collections import defaultdict
import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.responses import RedirectResponse

from .resources import security
from .resources.data_models import DMMQuery, KeywordsAppend, QueryEvent, UserCreate, UserEdit, UserProfile
from .resources.graph_helpers import (
    init_db,
    close_db,
    list_users,
    build_user_subgraph,
    delete_user_subgraph,
    load_user_profile,
)
from .resources.orcid_helpers import fetch_orcid_profile
from .resources.LLM_helpers import generate_keywords_from_session
from .resources.profile_helpers import (
    MAX_STORED_QUERIES,
    append_keywords,
    build_interest_profile,
    last_processed_at,
    remember_queries,
    stamp_keywords,
    weighted_keywords,
)
import httpx
import json

from typing import Any
from fastapi.security import OAuth2PasswordBearer

import threading

# for auth
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Crearte a logger for this module
logger = logging.getLogger(__name__)

# configuring the logger to track the refresh process 
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# set the attemps and the interval of attemps for the refresh
#   if the notify query is still not in the DMM
#       if the DMM is not reachable, the error is recorded in the logs
#       if after the attemp the refresh carries on
DMM_QUERY_ATTEMPTS = int(os.getenv("DMM_QUERY_ATTEMPTS", "3"))
DMM_QUERY_RETRY_SECONDS = float(os.getenv("DMM_QUERY_RETRY_SECONDS", "2"))

# Data managment model url
DMM_URL = os.getenv("DMM_URL", "https://datagems-dev.scayle.es/dmm").rstrip("/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    close_db()


app = FastAPI(
    title="User Profiler API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/swagger",
    redoc_url="/api/v1/redoc",
    root_path=os.getenv("ROOT_PATH", ""),
    lifespan=lifespan,
)

# Every route on this router requires a bearer token with this API in its audience
protected = APIRouter(dependencies=[Depends(security.require_app_scope)])


#=========================
# FUNCTIONS FOR INTERNAL USE
#=========================


def _save(profile: dict) -> UserProfile:
    """Rewrite the user's whole subgraph from a (modified) profile dict."""
    updated = UserProfile(**profile)
    delete_user_subgraph(updated.userId)
    build_user_subgraph(updated)
    return updated


def _require_user(user_id: str) -> dict:
    profile = load_user_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No such user: '{user_id}'")
    return profile


#--------------------------------
# User Creation

def _create(user_id: str, payload: UserCreate) -> UserProfile:
    '''
    Single place where a user is created
    
    input:
        - user_id (str): id of the user
        - payload (UserCreate): user data
        
    returns:
        - UserProfile: user profile
    '''
    data = payload.model_dump()
    data["keywords"] = stamp_keywords(data["keywords"], [])
    profile = UserProfile(userId=user_id, **data)
    build_user_subgraph(profile)
    return profile


def _user_from_token(claims: dict) -> UserCreate:
    '''
    User data available in the Keycloak token
    
    input:
        - claims (dict): info form the token
    '''
    return UserCreate(
        name=claims.get("given_name") or claims.get("preferred_username") or "-",
        surname=claims.get("family_name") or "-",
        email=claims.get("email") or "-",
        affiliation="unknown",
    )


#--------------------------------
# User Editing

def _apply_edit(current: dict, payload: UserEdit) -> UserProfile:
    '''
    Applies the fields set in payload to the profile and saves it
    '''
    previous_keywords = current["keywords"]
    for field, value in payload.model_dump(exclude_unset=True).items():
        current[field] = value
    # Keywords that already existed keep their timestamps, new (or never stamped) ones are stamped now
    current["keywords"] = stamp_keywords(current["keywords"], previous_keywords)
    return _save(current)


#-------------------------------
# User Creation from token

def _ensure_user(user_id: str, claims: dict) -> bool:
    '''
    (temporary)
    
    Creates the token's own user the first time the UP sees it
    Returns True if created.
    '''
    with _create_lock:
        if load_user_profile(user_id) is not None:
            return False
        if claims.get("sub") != user_id:
            raise HTTPException(status_code=404, detail=f"No such user: '{user_id}'")
        _create(user_id, _user_from_token(claims))
        logger.info("User %s not in the graph: created from the token", user_id)
        return True


#=========================================
# API endpoints
#=========================================

@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse(url="/api/v1")


@app.get("/api/v1")
async def api_home():
    return {"message": "User Profiler API V1 is running"}


@protected.get("/users", summary="List all users")
def get_users():
    users = list_users()
    return {"count": len(users), "users": users}


@protected.get("/user/{user_id}", summary="Retrieve a user by ID")
def get_user(user_id: str):
    return _require_user(user_id)


@protected.get("/user/{user_id}/profile", summary="Retrieve a portable interest profile for cross-service consumption")
def get_user_interest_profile(user_id: str):
    return build_interest_profile(_require_user(user_id))


@protected.get("/user/{user_id}/keywords", summary="List all keywords with their current weight, including expired ones")
def get_user_keywords(user_id: str):
    return {"keywords": weighted_keywords(_require_user(user_id))}


@protected.post("/user/{user_id}/keywords", summary="Append session keywords, refreshing the ones already present")
def append_user_keywords(user_id: str, payload: KeywordsAppend):
    current = _require_user(user_id)
    current["keywords"], added = append_keywords(current["keywords"], payload.keywords)
    _save(current)
    refreshed = [k for k in payload.keywords if k.strip() and k.strip() not in added]
    return {"added": added, "refreshed": refreshed}



#==============================
# User creation and deletion

# ensures the same user is not created twice by concurrent requests
_create_lock = threading.Lock()


# new endpoint for the UI
@protected.post("/user/me", status_code=201, summary="Create the token's own user, or complete it if it already exists")
def create_me(response: Response, payload: UserEdit | None = None,
              claims: dict = Depends(security.require_app_scope)):
    '''
    The user ID is the token's sub
        - new user: name, surname and email from the token, the body (e.g. {"affiliation": "..."})
          adds the missing fields or overrides the token's ones --> 201
        - existing user (e.g. already created by a QR notification): the body is applied
          as a PATCH --> 200
    '''
    
    # get user id from the token
    #   + user info
    user_id = claims["sub"]
    body = payload.model_dump(exclude_none=True) if payload else {}
    
    with _create_lock:
        current = load_user_profile(user_id)
        if current is None:
            return _create(user_id, UserCreate(**(_user_from_token(claims).model_dump() | body)))
        response.status_code = 200
        return _apply_edit(current, UserEdit(**body)) if body else UserProfile(**current)



# kept for testing
@protected.post("/user", status_code=201, summary="Dev: create a user with a random ID ")
def create_user(payload: UserCreate):
    return _create(str(uuid.uuid4()), payload)


# kept for testing
@protected.post("/user/{user_id}", status_code=201, summary="Dev: create a user with a given ID")
def create_user_with_id(user_id: str, payload: UserCreate):
    try:
        if str(uuid.UUID(user_id)) != user_id:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a lowercase, hyphenated UUID")
    with _create_lock:
        if load_user_profile(user_id) is not None:
            raise HTTPException(status_code=409, detail=f"User '{user_id}' already exists")
        return _create(user_id, payload)


@protected.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    return _apply_edit(_require_user(user_id), payload)


@protected.delete("/user/{user_id}", status_code=200, summary="Delete a user")
def delete_user(user_id: str):
    _require_user(user_id)
    delete_user_subgraph(user_id)
    return {"message": f"User '{user_id}' deleted."}


@protected.get("/orcid/{orcid_id}", summary="Fetch raw ORCID profile")
async def get_orcid_profile(orcid_id: str):
    return await fetch_orcid_profile(orcid_id)


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


#=============================
# Notify a new query

# to track the refresh process 
async def _refresh_in_background(user_id: str, token: str, query: str) -> None:
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




@protected.post("/user/{user_id}/queries", status_code=202, summary="Notify that the user has performed a new query (triggers a refresh)")
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


# ==============================
# TEST automatic refresh

@protected.post("/user/{user_id}/refresh-keyword_test", summary="Dev: refresh user's keywords from the DMM (for testing)")
async def refresh_keywords(user_id: str, token: str = Depends(oauth2_scheme)):
    '''
    refreshes user's keywords 
    
    Input:
        - user_id (str): id of the user
        - token (str): security check
    '''
    return await refresh_user_keywords(user_id, token)


#==============================
# TEST DMM connection

# for testing the DMM connection
@protected.get("/user/{user_id}/queries_test", summary="Dev: queries of a user, extracted from DMM")
async def get_user_queries(user_id: str, token: str = Depends(oauth2_scheme)):
    '''
    Returns user's queries
    Input:
        - user_id (str): id of the user of which the queries will be retrived
        - token: security check (auth)
    '''
    queries = await fetch_user_queries(token, user_id)
    return {"user_id": user_id, "count": len(queries), "queries": queries}


# =================================
# Generating user's kewywords


@protected.get("/user/{user_id}/generate-keywords", summary="Generate keywords from user sessions via LLM")
async def get_generated_keywords(user_id: str, token: str = Depends(oauth2_scheme)):
    profile = _require_user(user_id)
    
    # getting user previous queries
    user_queries = await fetch_user_queries(token, user_id)
    
    # generating the keywords
    result = generate_keywords_from_session(profile, queries=user_queries)
    
    if result is None:
        raise HTTPException(status_code=502, detail="The LLM could not be reached or returned an invalid response")
    return {"keywords": result}


# Included last: include_router copies the routes registered on the router so far
app.include_router(protected)
app.include_router(security.router, prefix="/api/v1")
