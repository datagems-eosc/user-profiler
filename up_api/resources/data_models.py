from typing import Optional
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator



# ---------------------------------------------------------------------------
# Node models  (mirrors PG-schema node types)
# ---------------------------------------------------------------------------

class Location(BaseModel):
    city: str
    country: str


class Keyword(BaseModel):
    value: str
    # Set on session keywords only: when first saved, and when last (re-)extracted.
    # lastSeenAt drives the keyword's weight in the interest profile.
    addedAt: Optional[datetime] = None
    lastSeenAt: Optional[datetime] = None


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
    dateOfBirth: Optional[datetime] = None
    email: str
    affiliation: str
    keywords: list[Keyword] = Field(default_factory=list)
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM output
# ---------------------------------------------------------------------------

class LLMSessionKeywords(BaseModel):
    """Shape the LLM is asked to reply with: {"keywords": ["...", "..."]}"""
    keywords: list[str]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    surname: str
    dateOfBirth: Optional[datetime] = None
    email: str
    affiliation: str
    keywords: list[Keyword] = Field(default_factory=list)
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


class KeywordsAppend(BaseModel):
    keywords: list[str]


class UserEdit(BaseModel):
    name: Optional[str] = None
    surname: Optional[str] = None
    dateOfBirth: Optional[datetime] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None
    keywords: Optional[list[Keyword]] = None
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: Optional[list[Session]] = None



#----------------------------------------------------------------------------
# Query event
#---------------------------------------------------------------------------

class DMMQuery(Query):
    '''
    Edits Query:
        - now tyepedAt is required and will be converted to UTC if not already
            --> It assumed that a time without timezone is in UTC
    '''
    
    typedAt: datetime

    @field_validator("typedAt")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class QueryEvent(BaseModel):
    '''
    Event body for a query event, used to notify about a new query
    '''
    query: str