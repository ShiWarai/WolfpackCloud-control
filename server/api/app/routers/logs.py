"""Чтение rosout-логов из InfluxDB."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.schemas import ErrorResponse, LogsStatusResponse, RosLogEntryResponse
from app.services import k8s as k8s_svc
from app.services import ros_logs_store
from app.services.influx import InfluxError, ping as influx_ping

router = APIRouter(prefix="/api/logs", tags=["logs"])
settings = get_settings()


def _build_logs_status(*, influxdb: str, rosout_bridge: str) -> LogsStatusResponse:
    message: str | None = None
    if influxdb == "disabled":
        message = "InfluxDB не настроен — логи не сохраняются."
    elif influxdb == "error":
        message = "InfluxDB недоступен — новые логи могут не записываться."
    elif rosout_bridge == "not_running":
        message = "rosout-bridge не запущен — логи из ROS не поступают."
    elif rosout_bridge == "unknown":
        message = "Не удалось проверить статус rosout-bridge в кластере."
    return LogsStatusResponse(
        influxdb=influxdb,
        rosout_bridge=rosout_bridge,
        message=message,
    )


@router.get("/status", response_model=LogsStatusResponse)
async def logs_status(_user: User = Depends(get_current_user)) -> LogsStatusResponse:
    influx_status = "disabled"
    if settings.influxdb_configured:
        try:
            influx_status = "connected" if await influx_ping(settings) else "error"
        except Exception:
            influx_status = "error"

    try:
        bridge_status = await asyncio.to_thread(k8s_svc.get_rosout_bridge_status, settings)
    except Exception:
        bridge_status = "unknown"

    return _build_logs_status(influxdb=influx_status, rosout_bridge=bridge_status)


@router.get(
    "",
    response_model=list[RosLogEntryResponse],
    responses={
        502: {"model": ErrorResponse, "description": "InfluxDB недоступен"},
    },
)
async def list_logs(
    network_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    _user: User = Depends(get_current_user),
) -> list[RosLogEntryResponse]:
    if not settings.influxdb_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="InfluxDB не настроен",
        )
    try:
        rows = await ros_logs_store.list_ros_logs(
            settings,
            network_id=network_id,
            limit=limit,
        )
    except InfluxError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InfluxDB: {exc}",
        ) from exc
    return [RosLogEntryResponse.model_validate(r) for r in rows]
