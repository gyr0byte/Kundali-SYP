"""Authenticated search for offline birthplace suggestions."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.core.permissions import Permission, require_permission
from app.geo.nepal import MAX_QUERY_LENGTH, Birthplace, search_birthplaces

router = APIRouter(
    prefix="/birthplaces",
    tags=["birthplaces"],
    dependencies=[Depends(require_permission(Permission.PROFILE_MANAGE_OWN))],
)


class BirthplaceQuery(BaseModel, extra="forbid"):
    query: str = Field(max_length=MAX_QUERY_LENGTH)


@router.post("/search", response_model=list[Birthplace])
def search(payload: BirthplaceQuery, response: Response) -> list[Birthplace]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return search_birthplaces(payload.query)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Enter 2 to 80 characters including letters to search birthplaces",
            headers={"Cache-Control": "no-store"},
        ) from None
