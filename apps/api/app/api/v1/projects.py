from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.dependencies import (
    DatabaseSession,
    OrganizationAdmin,
    OrganizationMember,
    enforce_trusted_origin,
)
from app.api.project_dependencies import ProjectAdmin, ProjectMember
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.project import ProjectCreate, ProjectData, ProjectListData, ProjectUpdate
from app.services.projects import create_project, list_projects, update_project

organization_projects_router = APIRouter(
    prefix="/organizations/{organization_id}/projects", tags=["projects"]
)
projects_router = APIRouter(prefix="/projects", tags=["projects"])


@organization_projects_router.get(
    "",
    response_model=ApiResponse[ProjectListData],
    summary="List projects in an organization",
)
async def organization_projects(
    organization_id: uuid.UUID,
    membership: OrganizationMember,
    db: DatabaseSession,
) -> ApiResponse[ProjectListData]:
    projects = await list_projects(db, membership.organization_id)
    return ApiResponse(data=ProjectListData(projects=projects, role=membership.role.value))


@organization_projects_router.post(
    "",
    response_model=ApiResponse[ProjectData],
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}},
    summary="Create a project as an organization owner or admin",
)
async def create_organization_project(
    organization_id: uuid.UUID,
    payload: ProjectCreate,
    request: Request,
    membership: OrganizationAdmin,
    db: DatabaseSession,
) -> ApiResponse[ProjectData]:
    enforce_trusted_origin(request)
    project = await create_project(
        db,
        organization_id=membership.organization_id,
        name=payload.name,
        environment=payload.environment,
        description=payload.description,
    )
    return ApiResponse(data=ProjectData(project=project, role=membership.role.value))


@projects_router.get(
    "/{project_id}",
    response_model=ApiResponse[ProjectData],
    responses={404: {"model": ErrorResponse}},
    summary="Get an accessible project",
)
async def project_detail(project_id: uuid.UUID, context: ProjectMember) -> ApiResponse[ProjectData]:
    return ApiResponse(
        data=ProjectData(project=context.project, role=context.membership.role.value)
    )


@projects_router.patch(
    "/{project_id}",
    response_model=ApiResponse[ProjectData],
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Update a project while keeping its slug stable",
)
async def update_project_detail(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    request: Request,
    context: ProjectAdmin,
    db: DatabaseSession,
) -> ApiResponse[ProjectData]:
    enforce_trusted_origin(request)
    project = await update_project(db, context.project, payload)
    return ApiResponse(data=ProjectData(project=project, role=context.membership.role.value))
