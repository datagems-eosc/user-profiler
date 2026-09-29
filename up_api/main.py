from contextlib import asynccontextmanager
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from .resources.data_models import UserCreate, UserEdit, UserProfile
from .resources.graph_helpers import (
    init_db,
    list_users,
    build_user_subgraph,
    delete_user_subgraph,
    load_user_profile,
)
from .resources.orcid_helpers import fetch_orcid_profile
from .resources.LLM_helpers import generate_keywords_from_session
from .resources.profile_helpers import build_interest_profile


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


@app.get("/users", summary="List all users")
def get_users():
    users = list_users()
    return {"count": len(users), "users": users}


@app.get("/user/{user_id}", summary="Retrieve a user by ID")
def get_user(user_id: str):
    return _require_user(user_id)


@app.get("/user/{user_id}/profile", summary="Retrieve a portable interest profile for cross-service consumption")
def get_user_interest_profile(user_id: str):
    return build_interest_profile(_require_user(user_id))


@app.post("/user", status_code=201, summary="Create a new user")
def create_user(payload: UserCreate):
    user_id = str(uuid.uuid4())
    profile = UserProfile(userId=user_id, **payload.model_dump())
    build_user_subgraph(profile)
    return profile


@app.delete("/user/{user_id}", status_code=200, summary="Delete a user")
def delete_user(user_id: str):
    _require_user(user_id)
    delete_user_subgraph(user_id)
    return {"message": f"User '{user_id}' deleted."}


@app.get("/orcid/{orcid_id}", summary="Fetch raw ORCID profile")
async def get_orcid_profile(orcid_id: str):
    return await fetch_orcid_profile(orcid_id)


@app.get("/user/{user_id}/generate-keywords", summary="Generate keywords from user sessions via LLM")
def get_generated_keywords(user_id: str):
    profile = _require_user(user_id)
    result = generate_keywords_from_session(profile)
    if result is None:
        raise HTTPException(status_code=502, detail="The LLM could not be reached or returned an invalid response")
    return {"keywords": result}


@app.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    current = _require_user(user_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        current[field] = value

    updated = UserProfile(**current)
    delete_user_subgraph(user_id)
    build_user_subgraph(updated)
    return updated
