from fastapi import APIRouter, Depends, Path, status

from app.db.models import User
from app.dependencies import get_claim_service, get_current_user
from app.schemas.claim import (
    ClaimCreateRequest,
    ClaimDecisionRequest,
    ClaimListResponse,
    ClaimResponse,
    ClaimSearchQuery,
)
from app.services.claim_service import ClaimService

router = APIRouter(tags=["claims"])


@router.post(
    "/items/{item_id}/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="File a claim against an item",
)
def file_claim(
    payload: ClaimCreateRequest,
    item_id: int = Path(..., ge=1),
    service: ClaimService = Depends(get_claim_service),
    current_user: User = Depends(get_current_user),
) -> ClaimResponse:
    claim = service.file_claim(item_id, payload, current_user)
    return ClaimResponse.model_validate(claim)


@router.get("/claims", response_model=ClaimListResponse, summary="List claims")
def list_claims(
    query: ClaimSearchQuery = Depends(),
    service: ClaimService = Depends(get_claim_service),
    current_user: User = Depends(get_current_user),
) -> ClaimListResponse:
    total, results = service.search(query, current_user)
    return ClaimListResponse(
        total=total,
        results=[ClaimResponse.model_validate(claim) for claim in results],
    )


@router.post(
    "/claims/{claim_id}/decision",
    response_model=ClaimResponse,
    summary="Approve or reject a claim (reporter only)",
)
def decide_claim(
    payload: ClaimDecisionRequest,
    claim_id: int = Path(..., ge=1),
    service: ClaimService = Depends(get_claim_service),
    current_user: User = Depends(get_current_user),
) -> ClaimResponse:
    claim = service.decide(claim_id, payload, current_user)
    return ClaimResponse.model_validate(claim)
