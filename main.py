from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime

app = FastAPI(title="User Profiler API")


# ---------------------------------------------------------------------------
# Node models  (mirrors PG-schema node types)
# ---------------------------------------------------------------------------

class Location(BaseModel):
    city: str
    country: str


class Keyword(BaseModel):
    value: str


class Author(BaseModel):
    fullName: str


class Publication(BaseModel):
    title: str
    doi: str
    journal: str
    year: int
    authors: list[Author] = Field(default_factory=list)   # HAS_AUTHOR edges


class ORCID(BaseModel):
    id: str
    keywords: list[Keyword] = Field(default_factory=list)           # HAS_KEYWORD edges
    publications: list[Publication] = Field(default_factory=list)   # HAS_PUBLICATION edges


class Query(BaseModel):
    text: str
    typedAt: Optional[datetime] = None


class Session(BaseModel):
    sessionId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    startTime: datetime
    endTime: Optional[datetime] = None
    queries: list[Query] = Field(default_factory=list)   # HAS_QUERY edges


# ---------------------------------------------------------------------------
# Full user profile  (User node + all outgoing edges collapsed into one object)
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    userId: str
    name: str
    surname: str
    age: int
    email: str
    affiliation: str
    location: Optional[Location] = None    # HAS_LOCATION edge
    orcid: Optional[ORCID] = None          # HAS_ORCID edge
    sessions: list[Session] = Field(default_factory=list)   # HAS_SESSION edges


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    surname: str
    age: int
    email: str
    affiliation: str
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


class UserEdit(BaseModel):
    name: Optional[str] = None
    surname: Optional[str] = None
    age: Optional[int] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: Optional[list[Session]] = None


# ---------------------------------------------------------------------------
# In-memory store  (swap for a graph-DB driver in production)
# ---------------------------------------------------------------------------

_db: dict[str, UserProfile] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/user/{user_id}", summary="Retrieve a user by ID")
def get_user(user_id: str):
    user = _db.get(user_id)
    if user is None:
        return {"message": f"No such user: '{user_id}'"}
    return user


@app.post("/user", status_code=201, summary="Create a new user")
def create_user(payload: UserCreate):
    user_id = str(uuid.uuid4())
    user = UserProfile(userId=user_id, **payload.model_dump())
    _db[user_id] = user
    return user


@app.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    user = _db.get(user_id)
    if user is None:
        return {"message": f"No such user: '{user_id}'"}

    merged = user.model_dump()
    for field, value in payload.model_dump(exclude_unset=True).items():
        merged[field] = value

    _db[user_id] = UserProfile(**merged)
    return _db[user_id]
