"""
Роутеры API.
"""

from app.routers.account import router as account_router
from app.routers.auth import router as auth_router
from app.routers.cluster import router as cluster_router
from app.routers.events import router as events_router
from app.routers.internal import router as internal_router
from app.routers.logs import router as logs_router
from app.routers.metrics import router as metrics_router
from app.routers.networks import router as networks_router
from app.routers.pairing import router as pairing_router
from app.routers.robots import router as robots_router
from app.routers.workloads import router as workloads_router

__all__ = [
    "account_router",
    "auth_router",
    "cluster_router",
    "events_router",
    "internal_router",
    "logs_router",
    "metrics_router",
    "networks_router",
    "pairing_router",
    "robots_router",
    "workloads_router",
]
