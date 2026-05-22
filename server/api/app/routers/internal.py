"""Внутренние эндпоинты (rosout-bridge, без JWT)."""

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import get_settings
from app.schemas import RosOutIngestBatch, RosOutIngestItem
from app.services import ros_logs_store
from app.services.influx import InfluxError

router = APIRouter(prefix="/api/internal", tags=["internal"])
settings = get_settings()


def _verify_ingest_token(x_ingest_token: str | None) -> None:
    if not x_ingest_token or x_ingest_token != settings.rosout_ingest_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid ingest token")


async def _write_items(items: list[RosOutIngestItem]) -> None:
    if not settings.influxdb_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="InfluxDB не настроен",
        )
    try:
        await ros_logs_store.write_ros_logs(settings, items)
    except InfluxError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InfluxDB: {exc}",
        ) from exc


@router.post("/rosout", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_rosout(
    body: RosOutIngestBatch,
    x_ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
) -> None:
    """Батч записей /rosout."""
    _verify_ingest_token(x_ingest_token)
    await _write_items(body.entries)


@router.post("/rosout/one", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_rosout_one(
    item: RosOutIngestItem,
    x_ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
) -> None:
    """Одна строка (удобно для простого bridge)."""
    _verify_ingest_token(x_ingest_token)
    await _write_items([item])
