from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.dependencies import CurrentAuth, DatabaseSession, enforce_trusted_origin
from app.api.project_dependencies import ProjectAdmin
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.project import (
    ApiKeyCreate,
    ApiKeyCreatedData,
    ApiKeyListData,
    ApiKeyRevokedData,
)
from app.services.project_api_keys import create_api_key, list_api_keys, revoke_api_key

router = APIRouter(prefix="/projects/{project_id}/api-keys", tags=["project API keys"])


@router.get(
    "",
    response_model=ApiResponse[ApiKeyListData],
    summary="List safe project API-key metadata",
)
async def keys(
    project_id: uuid.UUID, context: ProjectAdmin, db: DatabaseSession
) -> ApiResponse[ApiKeyListData]:
    keys_for_project = await list_api_keys(db, context.project.id)
    return ApiResponse(data=ApiKeyListData(api_keys=keys_for_project))


@router.post(
    "",
    response_model=ApiResponse[ApiKeyCreatedData],
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}},
    summary="Create a project API key; show its secret once",
)
async def create_key(
    project_id: uuid.UUID,
    payload: ApiKeyCreate,
    request: Request,
    context: ProjectAdmin,
    auth: CurrentAuth,
    db: DatabaseSession,
) -> ApiResponse[ApiKeyCreatedData]:
    enforce_trusted_origin(request)
    api_key, raw_key = await create_api_key(
        db,
        project=context.project,
        creator_id=auth.user.id,
        name=payload.name,
        expires_at=payload.expires_at,
    )
    return ApiResponse(data=ApiKeyCreatedData(api_key=api_key, raw_key=raw_key))


@router.post(
    "/{key_id}/revoke",
    response_model=ApiResponse[ApiKeyRevokedData],
    responses={404: {"model": ErrorResponse}},
    summary="Revoke a project API key",
)
async def revoke_key(
    project_id: uuid.UUID,
    key_id: uuid.UUID,
    request: Request,
    context: ProjectAdmin,
    db: DatabaseSession,
) -> ApiResponse[ApiKeyRevokedData]:
    enforce_trusted_origin(request)
    revoked = await revoke_api_key(db, project_id=context.project.id, key_id=key_id)
    return ApiResponse(data=ApiKeyRevokedData(api_key=revoked))
