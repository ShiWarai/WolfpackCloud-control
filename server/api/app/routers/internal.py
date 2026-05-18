"""Внутренние эндпоинты (rosout-bridge, без JWT)."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import RosLogEntry
from app.schemas import RosOutIngestBatch, RosOutIngestItem

router = APIRouter(prefix="/api/internal", tags=["internal"])
settings = get_settings()


def _verify_ingest_token(x_ingest_token: str | None) -> None:
    if not x_ingest_token or x_ingest_token != settings.rosout_ingest_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid ingest token")


@router.post("/rosout", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_rosout(
    body: RosOutIngestBatch,
    db: AsyncSession = Depends(get_db),
    x_ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
) -> None:
    """Батч записей /rosout."""
    _verify_ingest_token(x_ingest_token)
    for item in body.entries:
        db.add(
            RosLogEntry(
                network_id=item.network_id,
                ros_node_name=item.ros_node_name,
                level=item.level,
                message=item.message,
            )
        )
    await db.commit()


@router.post("/rosout/one", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_rosout_one(
    item: RosOutIngestItem,
    db: AsyncSession = Depends(get_db),
    x_ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
) -> None:
    """Одна строка (удобно для простого bridge)."""
    _verify_ingest_token(x_ingest_token)
    db.add(
        RosLogEntry(
            network_id=item.network_id,
            ros_node_name=item.ros_node_name,
            level=item.level,
            message=item.message,
        )
    )
    await db.commit()
