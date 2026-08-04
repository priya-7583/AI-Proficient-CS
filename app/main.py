from __future__ import annotations

from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import Settings, load_settings
from app.auth import AuthConfig, MutatingAuth
from app.db import Database
from app.models import (
    CreateLinkRequest,
    CreateLinkResponse,
    DeactivateLinkResponse,
    HealthResponse,
    LinkDetailsResponse,
    LinkStatsResponse,
)
from app.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.service import AliasInUseError, LinkExpiredError, LinkNotFoundError, LinkService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    db = Database(settings.db_path)
    db.initialize()
    service = LinkService(db, short_code_length=settings.short_code_length)

    limiter: RateLimiter = InMemoryRateLimiter(settings.create_limit_per_minute)
    if settings.redis_url:
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            redis_client.ping()
            limiter = RedisRateLimiter(settings.create_limit_per_minute, redis_client)
        except RedisError:
            # Keep service available if Redis is configured but unreachable.
            limiter = InMemoryRateLimiter(settings.create_limit_per_minute)

    auth = MutatingAuth(
        AuthConfig(
            require_auth=settings.require_mutating_auth,
            api_key=settings.api_key,
            jwt_secret=settings.jwt_secret,
            jwt_algorithm=settings.jwt_algorithm,
        )
    )

    app = FastAPI(title=settings.app_name, version="1.0.0")
    app.state.settings = settings

    def get_service() -> LinkService:
        return service

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(url_service: LinkService = Depends(get_service)) -> HealthResponse:
        return HealthResponse(status="ok", db_ok=url_service.healthcheck(), timestamp=datetime.now(UTC))

    @app.post("/api/v1/links", response_model=CreateLinkResponse, status_code=status.HTTP_201_CREATED)
    def create_link(
        payload: CreateLinkRequest,
        request: Request,
        url_service: LinkService = Depends(get_service),
    ) -> CreateLinkResponse:
        # Mutating routes require API key or JWT when auth is enabled.
        auth.authorize(request)
        identity = request.client.host if request.client else "unknown"
        if not limiter.allow(identity):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded for link creation",
            )

        try:
            created = url_service.create_link(
                original_url=str(payload.original_url),
                custom_alias=payload.custom_alias,
                created_by=payload.created_by,
                expires_in_minutes=payload.expires_in_minutes,
            )
        except AliasInUseError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"alias already in use: {exc}") from exc

        base = str(request.base_url).rstrip("/")
        return CreateLinkResponse(
            short_code=created["short_code"],
            short_url=f"{base}/{created['short_code']}",
            original_url=created["original_url"],
            created_at=created["created_at"],
            expires_at=created["expires_at"],
            already_exists=created["already_exists"],
        )

    @app.get("/{short_code}")
    def resolve_link(
        short_code: str,
        request: Request,
        url_service: LinkService = Depends(get_service),
    ) -> RedirectResponse:
        try:
            original = url_service.resolve_link(short_code)
        except LinkExpiredError as exc:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="short link expired") from exc
        except LinkNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="short link not found") from exc

        url_service.record_click(
            short_code=short_code,
            referrer=request.headers.get("referer"),
            user_agent=request.headers.get("user-agent"),
            client_ip=request.client.host if request.client else None,
        )
        return RedirectResponse(original, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @app.get("/api/v1/links/{short_code}", response_model=LinkDetailsResponse)
    def get_link(short_code: str, url_service: LinkService = Depends(get_service)) -> LinkDetailsResponse:
        try:
            details = url_service.get_link_details(short_code)
        except LinkNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="short link not found") from exc
        return LinkDetailsResponse(**details)

    @app.get("/api/v1/links/{short_code}/stats", response_model=LinkStatsResponse)
    def get_stats(short_code: str, url_service: LinkService = Depends(get_service)) -> LinkStatsResponse:
        try:
            stats = url_service.get_stats(short_code)
        except LinkNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="short link not found") from exc
        return LinkStatsResponse(**stats)

    @app.delete("/api/v1/links/{short_code}", response_model=DeactivateLinkResponse)
    def deactivate_link(
        short_code: str,
        request: Request,
        url_service: LinkService = Depends(get_service),
    ) -> DeactivateLinkResponse:
        auth.authorize(request)
        try:
            ok = url_service.deactivate(short_code)
        except LinkNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="short link not found") from exc
        return DeactivateLinkResponse(short_code=short_code, deactivated=ok)

    return app


app = create_app()
