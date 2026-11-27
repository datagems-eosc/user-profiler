'''
User management: internal helpers and endpoints to create, read, edit and delete users.
Covers both the token's own user (/user/me) and users by ID (/user/{user_id}).
'''
import logging, threading

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from ..resources import security
from ..resources.data_models import (
    ErrorDetail,
    KeywordList,
    KeywordsAppend,
    Message,
    UserCreate,
    UserEdit,
    UserMe,
    UserMeOut,
    UserProfile,
)
from ..resources.graph_helpers import (
    list_users,
    build_user_subgraph,
    delete_user_subgraph,
    load_user_profile,
)
from ..resources.orcid_helpers import fetch_orcid_profile
from ..resources.profile_helpers import (
    append_keywords,
    build_interest_profile,
    stamp_keywords,
    weighted_keywords,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ensures the same user is not created twice by concurrent requests
_create_lock = threading.Lock()

# shown in the OpenAPI document of the /user/me endpoints
_NO_PROFILE = {404: {"model": ErrorDetail, "description": "The token's user has no profile yet: create it with POST /user/me"}}


#=========================
# FUNCTIONS FOR INTERNAL USE
#=========================


def _save(profile: dict) -> UserProfile:
    """Rewrite the user's whole subgraph from a (modified) profile dict."""
    try:
        updated = UserProfile(**profile)
    except ValidationError as exc:
        # Safety net: the request models should already have rejected this. Nothing has been written yet
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors(include_url=False))) from exc
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
# User creation for unseen users (temporary)

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
# /me endpoint
#=========================================


# USER CREATION

# Every /user/me endpoint answers with UserMeOut (response_model): keywords and sessions are
# left out the same way everywhere, so the UI always gets the same object

# new endpoint for the UI
@router.post("/user/me", status_code=201, response_model=UserMeOut,
             responses={200: {"model": UserMeOut, "description": "The user already existed: the body was applied as an edit"}},
             summary="Create the token's own user, or complete it if it already exists")
def create_me(response: Response, payload: UserMe | None = None,
              claims: dict = Depends(security.require_app_scope)):
    '''
    The user ID is the token's sub
        - new user: name, surname and email from the token, the body (e.g. {"affiliation": "..."})
          adds the missing fields or overrides the token's ones --> 201
        - existing user (e.g. already created by a QR notification): the body is applied
          as a PATCH --> 200
    Safe to call every time the profile page opens: it never creates the user twice.
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
        return _apply_edit(current, UserEdit(**body)) if body else current


# USER PROFILE MANIPULATION


@router.get("/user/me", response_model=UserMeOut, responses=_NO_PROFILE, summary="Retrieve the token's own user")
def get_me(claims: dict = Depends(security.require_app_scope)):
    return _require_user(claims["sub"])


@router.patch("/user/me", response_model=UserMeOut, responses=_NO_PROFILE, summary="Edit the token's own user")
def edit_me(payload: UserMe, claims: dict = Depends(security.require_app_scope)):
    '''
    Only the fields in the body change. null clears dateOfBirth, location and orcid;
    the required fields (name, surname, email, affiliation) cannot be null or empty.
    location and orcid are replaced as a whole.
    '''
    return _apply_edit(_require_user(claims['sub']), UserEdit(**payload.model_dump(exclude_unset=True)))


@router.delete("/user/me", response_model=Message, responses=_NO_PROFILE, summary="Delete the token's own user")
def delete_me(claims: dict = Depends(security.require_app_scope)):
    _require_user(claims['sub'])
    delete_user_subgraph(claims['sub'])
    return {"message": f"User '{claims['sub']}' deleted."}


#=========================================
# /{user_id} endpoint
#=========================================

@router.get("/users", summary="List all users")
def get_users():
    users = list_users()
    return {"count": len(users), "users": users}


@router.get("/user/{user_id}", summary="Retrieve a user by ID")
def get_user(user_id: str):
    return _require_user(user_id)


@router.get("/user/{user_id}/profile", summary="Retrieve a portable interest profile for cross-service consumption")
def get_user_interest_profile(user_id: str):
    return build_interest_profile(_require_user(user_id))


@router.get("/user/{user_id}/keywords", response_model=KeywordList,
            summary="List all keywords with their current weight, including expired ones")
def get_user_keywords(user_id: str):
    return {"keywords": weighted_keywords(_require_user(user_id))}


@router.post("/user/{user_id}/keywords", summary="Append session keywords, refreshing the ones already present")
def append_user_keywords(user_id: str, payload: KeywordsAppend):
    current = _require_user(user_id)
    current["keywords"], added = append_keywords(current["keywords"], payload.keywords)
    _save(current)
    refreshed = [k for k in payload.keywords if k.strip() and k.strip() not in added]
    return {"added": added, "refreshed": refreshed}


@router.patch("/user/{user_id}", summary="Edit an existing user")
def edit_user(user_id: str, payload: UserEdit):
    return _apply_edit(_require_user(user_id), payload)


@router.delete("/user/{user_id}", status_code=200, summary="Delete a user")
def delete_user(user_id: str):
    _require_user(user_id)
    delete_user_subgraph(user_id)
    return {"message": f"User '{user_id}' deleted."}


@router.get("/orcid/{orcid_id}", summary="Fetch raw ORCID profile")
async def get_orcid_profile(orcid_id: str):
    return await fetch_orcid_profile(orcid_id)
