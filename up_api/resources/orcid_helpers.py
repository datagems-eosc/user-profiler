import httpx
from fastapi import HTTPException

ORCID_PUBLIC_API = "https://pub.orcid.org/v3.0"


async def fetch_orcid_profile(orcid_id: str, endpoint: str = "") -> dict:
    url = f"{ORCID_PUBLIC_API}/{orcid_id}/{endpoint}".rstrip("/")
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers={"Accept": "application/json"})

    if response.status_code == 200:
        return response.json()
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"ORCID profile not found: '{orcid_id}'")
    raise HTTPException(status_code=response.status_code, detail="ORCID API error")
