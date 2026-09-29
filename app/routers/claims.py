from fastapi import APIRouter, Depends, Path, status

from app.db.models import User
from app.dependencies import get_claim_service, get_current_user
from app.schemas.auth import PublicUserResponse
from app.schemas.claim import (
    ClaimCreateRequest,
    ClaimDecisionRequest,
    ClaimListResponse,
    ClaimResponse,
    ClaimSearchQuery,
)
from app.services.claim_service import ClaimService

router = APIRouter(tags=["claims"])


def _serialise(claim, service: ClaimService, viewer: User) -> ClaimResponse:
    """Render a claim for one particular viewer.

    Both parties are carried on the response so the claimant can see who to
    contact without a second request. Their addresses are attached only once
    the claim is approved, and only for the two people it is between -- the
    viewer is one of them, so "both" means "the other person, plus your own
    address back". Every other reader gets names only.
    """
    disclose = service.contact_disclosed_to(claim, viewer)
    return ClaimResponse(
        id=claim.id,
        item_id=claim.item_id,
        item_name=claim.item.name if claim.item else None,
        status=claim.status,
        evidence=claim.evidence,
        created_at=claim.created_at,
        decided_at=claim.decided_at,
        claimant=PublicUserResponse.of(claim.claimant, disclose_contact=disclose),
        reporter=(
            PublicUserResponse.of(claim.item.reporter, disclose_contact=disclose)
            if claim.item
            else None
        ),
    )


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
    return _serialise(claim, service, current_user)


@router.get("/claims", response_model=ClaimListResponse, summary="List claims")
def list_claims(
    query: ClaimSearchQuery = Depends(),
    service: ClaimService = Depends(get_claim_service),
    current_user: User = Depends(get_current_user),
) -> ClaimListResponse:
    total, results = service.search(query, current_user)
    return ClaimListResponse(
        total=total,
        results=[_serialise(claim, service, current_user) for claim in results],
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
    return _serialise(claim, service, current_user)
