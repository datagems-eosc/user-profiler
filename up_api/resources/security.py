"""
Bearer-token authentication against the DataGEMS Keycloak realm.

Adapted from data-model-management's dmm_api/resources/security.py: tokens are
verified with the realm's public keys (JWKS), then the audience is checked
against this API's client ID.
"""
import logging
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

logger = logging.getLogger(__name__)

OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "user-profiler")
OIDC_ISSUER_URL: str = os.getenv(
    "OIDC_ISSUER_URL", "https://datagems-dev.scayle.es/oauth/realms/dev"
)
OIDC_JWKS_URL: str = os.getenv(
    "OIDC_JWKS_URL", f"{OIDC_ISSUER_URL}/protocol/openid-connect/certs"
)

HTTP_TIMEOUT_SECONDS = 10.0
JWKS_CACHE_TTL_SECONDS = int(os.getenv("JWKS_CACHE_TTL_SECONDS", "300"))
JWT_SIGNING_ALGORITHM = "RS256"

_bearer_scheme = HTTPBearer(auto_error=False)
_jwks_cache = None
_jwks_cache_expires_at = 0.0

router = APIRouter()


class AuthTestRequest(BaseModel):
    """Input payload for the basic auth test endpoint (same shape as the other DataGEMS APIs)."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr
    k: StrictInt


async def _get_jwks() -> dict[str, Any]:
    """Return the realm's public keys, cached for JWKS_CACHE_TTL_SECONDS
    (so a key rotation can take up to that long to be picked up)."""
    global _jwks_cache, _jwks_cache_expires_at

    if _jwks_cache and time.time() < _jwks_cache_expires_at:
        return _jwks_cache

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(OIDC_JWKS_URL)
        response.raise_for_status()
        _jwks_cache = response.json()

    _jwks_cache_expires_at = time.time() + JWKS_CACHE_TTL_SECONDS
    return _jwks_cache


async def require_valid_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency: checks `Authorization: Bearer <token>` for a valid signature,
    issuer and expiry, and returns the decoded claims.
    Raises 401 for a missing/invalid token, 503 if the public keys cannot be fetched.
    The audience is checked separately by require_app_scope.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            await _get_jwks(),
            algorithms=[JWT_SIGNING_ALGORITHM],
            issuer=OIDC_ISSUER_URL,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not fetch JWKS: {exc}",
        ) from exc

    return payload


async def require_app_scope(
    token_payload: dict[str, Any] = Depends(require_valid_token),
) -> dict[str, Any]:
    """FastAPI dependency: on top of require_valid_token, checks that OIDC_CLIENT_ID
    is in the token's audience (`aud` can be a string or a list). Raises 403 otherwise."""
    aud = token_payload.get("aud", [])
    audiences = aud if isinstance(aud, list) else [aud] if aud else []

    if OIDC_CLIENT_ID not in audiences:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token missing required audience: {OIDC_CLIENT_ID}",
        )

    return token_payload


@router.post("/authtest", summary="Check that a bearer token is accepted by this API")
async def authtest(
    payload: AuthTestRequest,
    token_payload: dict[str, Any] = Depends(require_app_scope),
):
    """Validate caller token (signature, issuer and audience) and echo minimal identity + request payload."""
    return {
        "authorized": True,
        "message": "Token is valid",
        "request": payload.model_dump(),
        "subject": token_payload.get("sub"),
        "username": token_payload.get("preferred_username"),
    }
