from typing import Optional
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    authors: list[Author] = Field(default_factory=list)


class ORCID(BaseModel):
    id: str
    keywords: list[Keyword] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)


class Query(BaseModel):
    text: str
    typedAt: Optional[datetime] = None


class Session(BaseModel):
    sessionId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    startTime: datetime
    endTime: Optional[datetime] = None
    extracted: bool = False
    queries: list[Query] = Field(default_factory=list)


class UserProfile(BaseModel):
    userId: str
    name: str
    surname: str
    age: int
    email: str
    affiliation: str
    keywords: list[Keyword] = Field(default_factory=list)
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    surname: str
    age: int
    email: str
    affiliation: str
    keywords: list[Keyword] = Field(default_factory=list)
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


class UserEdit(BaseModel):
    name: Optional[str] = None
    surname: Optional[str] = None
    age: Optional[int] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None
    keywords: Optional[list[Keyword]] = None
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: Optional[list[Session]] = None
