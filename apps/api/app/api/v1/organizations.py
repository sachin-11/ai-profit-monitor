from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.api.dependencies import (
    CurrentAuth,
    DatabaseSession,
    OrganizationAdmin,
    OrganizationMember,
    enforce_trusted_origin,
)
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.organization import (
    MemberListData,
    MemberPublic,
    OrganizationData,
    OrganizationListData,
    OrganizationMembership,
    OrganizationUpdateRequest,
)
from app.services.organizations import (
    list_memberships,
    list_organization_members,
    update_organization_name,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get(
    "",
    response_model=ApiResponse[OrganizationListData],
    summary="List the current user's organizations",
)
async def organizations(
    auth: CurrentAuth, db: DatabaseSession
) -> ApiResponse[OrganizationListData]:
    memberships = await list_memberships(db, auth.user.id)
    return ApiResponse(
        data=OrganizationListData(
            organizations=[
                OrganizationMembership(organization=item.organization, role=item.role)
                for item in memberships
            ]
        )
    )


@router.get(
    "/{organization_id}",
    response_model=ApiResponse[OrganizationData],
    responses={404: {"model": ErrorResponse}},
    summary="Get an organization available to the current user",
)
async def organization(
    organization_id: uuid.UUID,
    membership: OrganizationMember,
) -> ApiResponse[OrganizationData]:
    return ApiResponse(
        data=OrganizationData(organization=membership.organization, role=membership.role)
    )


@router.patch(
    "/{organization_id}",
    response_model=ApiResponse[OrganizationData],
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Rename an organization without changing its stable slug",
)
async def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdateRequest,
    request: Request,
    membership: OrganizationAdmin,
    db: DatabaseSession,
) -> ApiResponse[OrganizationData]:
    enforce_trusted_origin(request)
    updated = await update_organization_name(db, membership, payload.name)
    return ApiResponse(data=OrganizationData(organization=updated.organization, role=updated.role))


@router.get(
    "/{organization_id}/members",
    response_model=ApiResponse[MemberListData],
    responses={404: {"model": ErrorResponse}},
    summary="List safe member information for an organization",
)
async def members(
    organization_id: uuid.UUID,
    membership: OrganizationMember,
    db: DatabaseSession,
) -> ApiResponse[MemberListData]:
    rows = await list_organization_members(db, membership.organization_id)
    return ApiResponse(
        data=MemberListData(
            members=[
                MemberPublic(
                    membership_id=item.id,
                    user_id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    role=item.role,
                    joined_at=item.created_at,
                )
                for item, user in rows
            ]
        )
    )
