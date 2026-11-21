"""
Главный модуль FastAPI — WolfpackCloud Control API.
"""

from contextlib import asynccontextmanager
import logging
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app import __version__
from app.config import get_settings
from app.database import engine, init_db
from app.routers import (
    account_router,
    auth_router,
    cluster_router,
    events_router,
    internal_router,
    logs_router,
    metrics_router,
    networks_router,
    pairing_router,
    robots_router,
    workloads_router,
)
from app.openapi_keycloak import patch_openapi_for_keycloak_swagger
from app.schemas import ErrorResponse, HealthResponse
from app.services.influx import ping as influx_ping
from app.tasks import start_scheduler, stop_scheduler
from sqlalchemy import text

settings = get_settings()


def _configure_app_package_logging() -> None:
    """Uvicorn оставляет root на WARNING — иначе INFO от app.* не попадает в stdout (kubectl logs)."""
    log = logging.getLogger("app")
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
    log.addHandler(handler)
    log.propagate = False


_configure_app_package_logging()

# OAuth login в Swagger — только публичный SPA-клиент; не путать с JWT audience/resource server.
_swagger_oauth_client_id = (settings.keycloak_swagger_client_id or "").strip() or "wolfpack-control-web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


_api_docs_url = "/api/docs" if settings.debug else None
_api_redoc_url = "/api/redoc" if settings.debug else None
_api_openapi_url = "/api/openapi.json" if settings.debug else None

app = FastAPI(
    title=settings.app_name,
    description=(
        "Управление кластером WolfpackCloud (k8s, роботы, сети ROS, Keycloak OIDC). "
        "**Authorize:** схема **KeycloakOIDC** — вход через Keycloak (authorization code + PKCE); "
        "в форме OAuth поле **client_id** = **`wolfpack-control-web`** (не логин пользователя); "
        "либо **HTTPBearer** — вставить access token вручную."
    ),
    version=__version__,
    docs_url=_api_docs_url,
    redoc_url=_api_redoc_url,
    openapi_url=_api_openapi_url,
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect" if settings.debug else None,
    swagger_ui_init_oauth={
        "clientId": _swagger_oauth_client_id,
        "appName": settings.app_name,
        "usePkceWithAuthorizationCodeGrant": True,
        "scopes": "openid profile email",
    }
    if settings.debug
    else None,
    swagger_ui_parameters={
        "persistAuthorization": True,
    }
    if settings.debug
    else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            detail="Внутренняя ошибка сервера",
            error_code="INTERNAL_ERROR",
        ).model_dump(),
    )


app.include_router(internal_router)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(networks_router)
app.include_router(cluster_router)
app.include_router(events_router)
app.include_router(workloads_router)
app.include_router(logs_router)
app.include_router(metrics_router)
app.include_router(pairing_router)
app.include_router(robots_router)

if settings.debug:
    patch_openapi_for_keycloak_swagger(app, issuer=settings.keycloak_issuer)


@app.get("/docs", include_in_schema=False)
async def redirect_legacy_docs() -> RedirectResponse:
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return RedirectResponse(url="/api/docs", status_code=307)


@app.get("/openapi.json", include_in_schema=False)
async def redirect_legacy_openapi_json() -> RedirectResponse:
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return RedirectResponse(url="/api/openapi.json", status_code=307)


@app.get("/redoc", include_in_schema=False)
async def redirect_legacy_redoc() -> RedirectResponse:
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return RedirectResponse(url="/api/redoc", status_code=307)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> dict[str, Any]:
    db_status = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    influx_status = "disabled"
    if settings.influxdb_configured:
        try:
            influx_status = "connected" if await influx_ping(settings) else "error"
        except Exception:
            influx_status = "error"
    return {
        "status": "ok",
        "version": __version__,
        "database": db_status,
        "metrics_backend": "heartbeat_only",
        "influxdb": influx_status,
    }


@app.get("/", tags=["system"])
async def root() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": settings.app_name,
        "version": __version__,
        "health": "/health",
    }
    if settings.debug:
        payload.update(
            {
                "openapi": "/api/openapi.json",
                "swagger_ui": "/api/docs",
                "redoc": "/api/redoc",
            }
        )
    return payload
