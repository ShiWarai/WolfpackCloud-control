"""Чтение событий деплоя из InfluxDB."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.schemas import DeploymentEventResponse, ErrorResponse
from app.services import deployment_events_store
from app.services.influx import InfluxError

router = APIRouter(prefix="/api/events", tags=["events"])
settings = get_settings()


@router.get(
    "/deployments",
    response_model=list[DeploymentEventResponse],
    responses={
        502: {"model": ErrorResponse, "description": "InfluxDB недоступен"},
    },
    summary="События деплоя и миграций",
)
async def list_deployment_events(
    deployment: str | None = Query(None, description="Фильтр по имени Deployment"),
    status_filter: str | None = Query(None, alias="status", description="Фильтр по статусу"),
    limit: int = Query(200, ge=1, le=2000),
    _user: User = Depends(get_current_user),
) -> list[DeploymentEventResponse]:
    if not settings.influxdb_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="InfluxDB не настроен",
        )
    try:
        rows = await deployment_events_store.list_deployment_events(
            settings,
            deployment=deployment,
            status=status_filter,
            limit=limit,
        )
    except InfluxError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InfluxDB: {exc}",
        ) from exc
    return [DeploymentEventResponse.model_validate(r) for r in rows]
