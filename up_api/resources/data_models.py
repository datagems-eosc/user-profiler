from typing import Annotated, Literal, Optional
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator


# Required text fields sent by clients: surrounding spaces are trimmed, and empty values are rejected
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]



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
    name: NonEmptyStr
    surname: NonEmptyStr
    dateOfBirth: Optional[datetime] = None
    email: NonEmptyStr
    affiliation: NonEmptyStr
    keywords: list[Keyword] = Field(default_factory=list)
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: list[Session] = Field(default_factory=list)


class KeywordsAppend(BaseModel):
    keywords: list[str]


def _reject_nulls(model: BaseModel, fields: tuple[str, ...]) -> BaseModel:
    '''
    In a PATCH body, a field left out means "don't change it", while null means "clear it".
    Required fields (and lists) cannot be cleared: an explicit null is a 422, not a 500 on save.
    '''
    nulls = [f for f in fields if f in model.model_fields_set and getattr(model, f) is None]
    if nulls:
        raise ValueError(f"{', '.join(nulls)} cannot be null: leave the field out to keep its value")
    return model


class UserEdit(BaseModel):
    name: Optional[NonEmptyStr] = None
    surname: Optional[NonEmptyStr] = None
    dateOfBirth: Optional[datetime] = None
    email: Optional[NonEmptyStr] = None
    affiliation: Optional[NonEmptyStr] = None
    keywords: Optional[list[Keyword]] = None
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None
    sessions: Optional[list[Session]] = None

    @model_validator(mode="after")
    def _no_null_required(self):
        return _reject_nulls(self, ("name", "surname", "email", "affiliation", "keywords", "sessions"))



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
    
    

#----------------------------------------------------------------------------
# User's profile edit
#---------------------------------------------------------------------------

class UserMe(BaseModel):
    '''
    Fields the user can edit from the UI
        --> excluding sessions and keywords
    Send only the fields that change. null clears dateOfBirth, location and orcid,
    and is rejected for the required fields.
    '''
    name: Optional[NonEmptyStr] = None
    surname: Optional[NonEmptyStr] = None
    dateOfBirth: Optional[datetime] = None
    email: Optional[NonEmptyStr] = None
    affiliation: Optional[NonEmptyStr] = None
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None

    @model_validator(mode="after")
    def _no_null_required(self):
        return _reject_nulls(self, ("name", "surname", "email", "affiliation"))


#----------------------------------------------------------------------------
# Responses of the UI-facing endpoints (the contract shown in the OpenAPI document)
#---------------------------------------------------------------------------

class UserMeOut(BaseModel):
    '''
    The token's own user, as returned by every /user/me endpoint
        --> without keywords (see /user/me/keywords) and sessions (the UI shows the queries itself)
    '''
    userId: str
    name: str
    surname: str
    dateOfBirth: Optional[datetime] = None
    email: str
    affiliation: str
    location: Optional[Location] = None
    orcid: Optional[ORCID] = None


class WeightedKeyword(BaseModel):
    value: str
    weight: float = Field(description="1.0 when just seen, halves every KEYWORD_HALF_LIFE_DAYS; constant for ORCID keywords")
    source: Literal["session", "orcid"]
    lastSeenAt: Optional[datetime] = Field(None, description="Last time the keyword was extracted; null for ORCID keywords")
    expired: bool = Field(description="Below KEYWORD_MIN_WEIGHT: no longer used by other services")


class KeywordList(BaseModel):
    keywords: list[WeightedKeyword]


KeywordStatus = Literal["ok", "pending", "no_queries", "no_keywords", "error", "no_profile"]


class MyKeywords(BaseModel):
    '''
    Keywords of the token's own user, with what the UI should show when there are none
    '''
    status: KeywordStatus = Field(description=(
        "ok: keywords available | pending: a refresh is running, ask again in a few seconds | "
        "no_queries: the DMM has no queries for the user yet | no_keywords: the queries were processed, "
        "but no keywords came out | error: the last refresh failed (DMM or LLM), it is retried later | "
        "no_profile: the user has no profile yet"))
    keywords: list[WeightedKeyword]


class Message(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    '''Body of the error responses (FastAPI format)'''
    detail: str