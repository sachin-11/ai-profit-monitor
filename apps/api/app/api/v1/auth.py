from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import CurrentAuth, DatabaseSession, enforce_trusted_origin
from app.core.errors import ApiError
from app.core.security import LoginRateLimiter, normalize_email
from app.schemas.auth import (
    LoginData,
    LoginRequest,
    LogoutData,
    MeData,
    MembershipPublic,
    RegisterData,
    RegisterRequest,
)
from app.schemas.common import ApiResponse, ErrorResponse
from app.services.auth import (
    authenticate_user,
    get_user_memberships,
    register_user,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


def _clear_session_cookie(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


@router.post(
    "/register",
    response_model=ApiResponse[RegisterData],
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
    summary="Register a user and organization",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> ApiResponse[RegisterData]:
    enforce_trusted_origin(request)
    settings = request.app.state.settings
    if len(payload.password) < settings.password_min_length:
        raise ApiError(
            422,
            "password_too_short",
            f"Password must be at least {settings.password_min_length} characters",
        )
    result = await register_user(
        db,
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
        organization_name=payload.organization_name,
        settings=settings,
    )
    _set_session_cookie(request, response, result.raw_session_token)
    membership = MembershipPublic(
        id=result.membership.id,
        role=result.membership.role,
        created_at=result.membership.created_at,
        organization=result.organization,
    )
    return ApiResponse(
        data=RegisterData(
            user=result.user,
            organization=result.organization,
            membership=membership,
        )
    )


@router.post(
    "/login",
    response_model=ApiResponse[LoginData],
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Create a server-side session",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> ApiResponse[LoginData]:
    enforce_trusted_origin(request)
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{normalize_email(str(payload.email))}"
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    if not limiter.is_allowed(rate_key):
        raise ApiError(429, "login_rate_limited", "Too many login attempts; try again later")

    result = await authenticate_user(
        db,
        email=str(payload.email),
        password=payload.password,
        settings=request.app.state.settings,
    )
    if result is None:
        limiter.record_failure(rate_key)
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    limiter.reset(rate_key)
    _set_session_cookie(request, response, result.raw_session_token)
    return ApiResponse(data=LoginData(user=result.user))


@router.post(
    "/logout",
    response_model=ApiResponse[LogoutData],
    summary="Revoke the current session",
)
async def logout(
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> ApiResponse[LogoutData]:
    enforce_trusted_origin(request)
    settings = request.app.state.settings
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        await revoke_session(db, raw_token)
    _clear_session_cookie(request, response)
    return ApiResponse(data=LogoutData())


@router.get(
    "/me",
    response_model=ApiResponse[MeData],
    responses={401: {"model": ErrorResponse}},
    summary="Get the authenticated profile",
)
async def me(auth: CurrentAuth, db: DatabaseSession) -> ApiResponse[MeData]:
    memberships = await get_user_memberships(db, auth.user.id)
    public_memberships = [
        MembershipPublic(
            id=membership.id,
            role=membership.role,
            created_at=membership.created_at,
            organization=membership.organization,
        )
        for membership in memberships
    ]
    return ApiResponse(data=MeData(user=auth.user, memberships=public_memberships))
