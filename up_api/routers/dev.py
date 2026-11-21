'''
Endpoints kept for testing only, not used by the UI or the QR:
    - creation of users with random/given ID
    - manual keyword refresh
    - DMM connection check.
'''
import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..resources.data_models import UserCreate
from ..resources.graph_helpers import load_user_profile
from .user import _create, _create_lock
from .keywords import fetch_user_queries, oauth2_scheme, refresh_user_keywords

router = APIRouter()


#==============================
# User creation

@router.post("/user", status_code=201, summary="Dev: create a user with a random ID ")
def create_user(payload: UserCreate):
    return _create(str(uuid.uuid4()), payload)


@router.post("/user/{user_id}", status_code=201, summary="Dev: create a user with a given ID")
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


# ==============================
# TEST automatic refresh

@router.post("/user/{user_id}/refresh-keyword_test", summary="Dev: refresh user's keywords from the DMM (for testing)")
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

@router.get("/user/{user_id}/queries_test", summary="Dev: queries of a user, extracted from DMM")
async def get_user_queries(user_id: str, token: str = Depends(oauth2_scheme)):
    '''
    Returns user's queries
    Input:
        - user_id (str): id of the user of which the queries will be retrived
        - token: security check (auth)
    '''
    queries = await fetch_user_queries(token, user_id)
    return {"user_id": user_id, "count": len(queries), "queries": queries}
