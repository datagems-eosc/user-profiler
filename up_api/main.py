from contextlib import asynccontextmanager
import os
import uuid

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from .resources import security
from .resources.data_models import KeywordsAppend, UserCreate, UserEdit, UserProfile
from .resources.graph_helpers import (
    init_db,
    list_users,
    build_user_subgraph,
    delete_user_subgraph,
    load_user_profile,
)
from .resources.orcid_helpers import fetch_orcid_profile
from .resources.LLM_helpers import generate_keywords_from_session
from .resources.profile_helpers import (
    append_keywords,
    build_interest_profile,
    stamp_keywords,
    weighted_keywords,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


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


@protected.post("/user", status_code=201, summary="Create a new user")
def create_user(payload: UserCreate):
    user_id = str(uuid.uuid4())
    data = payload.model_dump()
    data["keywords"] = stamp_keywords(data["keywords"], [])
    profile = UserProfile(userId=user_id, **data)
    build_user_subgraph(profile)
    return profile


@protected.delete("/user/{user_id}", status_code=200, summary="Delete a user")
def delete_user(user_id: str):
    _require_user(user_id)
    delete_user_subgraph(user_id)
    return {"message": f"User '{user_id}' deleted."}


@protected.get("/orcid/{orcid_id}", summary="Fetch raw ORCID profile")
async def get_orcid_profile(orcid_id: str):
    return await fetch_orcid_profile(orcid_id)


@protected.get("/user/{user_id}/generate-keywords", summary="Generate keywords from user sessions via LLM")
def get_generated_keywords(user_id: str):
    profile = _require_user(user_id)
    result = generate_keywords_from_session(profile)
    if result is None:
        raise HTTPException(status_code=502, detail="The LLM could not be reached or returned an invalid response")
    return {"keywords": result}


@protected.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    current = _require_user(user_id)
    previous_keywords = current["keywords"]

    for field, value in payload.model_dump(exclude_unset=True).items():
        current[field] = value

    # Keywords that already existed keep their timestamps, new (or never stamped) ones are stamped now
    current["keywords"] = stamp_keywords(current["keywords"], previous_keywords)
    return _save(current)


# Included last: include_router copies the routes registered on the router so far
app.include_router(protected)
app.include_router(security.router, prefix="/api/v1")
