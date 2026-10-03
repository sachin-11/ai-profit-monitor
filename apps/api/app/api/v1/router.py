from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.project_api_keys import router as api_keys_router
from app.api.v1.project_events import router as project_events_router
from app.api.v1.projects import organization_projects_router, projects_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(organizations_router)
router.include_router(organization_projects_router)
router.include_router(projects_router)
router.include_router(api_keys_router)
router.include_router(ingest_router)
router.include_router(project_events_router)
