from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI

from .resources.data_models import UserCreate, UserEdit, UserProfile
from .resources.graph_helpers import (
    init_db,
    list_user_ids,
    build_user_subgraph,
    delete_user_subgraph,
    load_user_profile,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="User Profiler API", lifespan=lifespan)


@app.get("/users", summary="List all user IDs")
def list_users():
    ids = list_user_ids()
    return {"count": len(ids), "userIds": ids}


@app.get("/user/{user_id}", summary="Retrieve a user by ID")
def get_user(user_id: str):
    profile = load_user_profile(user_id)
    if profile is None:
        return {"message": f"No such user: '{user_id}'"}
    return profile


@app.post("/user", status_code=201, summary="Create a new user")
def create_user(payload: UserCreate):
    user_id = str(uuid.uuid4())
    profile = UserProfile(userId=user_id, **payload.model_dump())
    build_user_subgraph(profile)
    return profile


@app.delete("/user/{user_id}", status_code=200, summary="Delete a user")
def delete_user(user_id: str):
    if load_user_profile(user_id) is None:
        return {"message": f"No such user: '{user_id}'"}
    delete_user_subgraph(user_id)
    return {"message": f"User '{user_id}' deleted."}


@app.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    current = load_user_profile(user_id)
    if current is None:
        return {"message": f"No such user: '{user_id}'"}

    for field, value in payload.model_dump(exclude_unset=True).items():
        current[field] = value

    updated = UserProfile(**current)
    delete_user_subgraph(user_id)
    build_user_subgraph(updated)
    return updated
