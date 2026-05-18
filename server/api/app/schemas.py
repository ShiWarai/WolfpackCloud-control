"""
Pydantic схемы для валидации запросов и ответов API.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import Architecture, PairCodeStatus, RobotStatus, UserRole, WorkloadStatus

__all__ = [
    "Architecture",
    "PairCodeStatus",
    "RobotStatus",
    "UserRole",
    "WorkloadStatus",
]


# =============================================================================
# Схемы для пользователей и аутентификации
# =============================================================================


class UserCreate(BaseModel):
    """Схема для регистрации пользователя."""

    email: EmailStr = Field(..., description="Email пользователя")
    password: str = Field(..., min_length=8, max_length=128, description="Пароль")
    name: str = Field(..., min_length=1, max_length=255, description="Имя пользователя")


class UserLogin(BaseModel):
    """Схема для входа пользователя."""

    email: EmailStr = Field(..., description="Email пользователя")
    password: str = Field(..., description="Пароль")


class UserResponse(BaseModel):
    """Схема ответа с информацией о пользователе."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool
    keycloak_sub: str | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    """Схема для обновления пользователя."""

    name: str | None = Field(None, min_length=1, max_length=255)


class TokenResponse(BaseModel):
    """Схема ответа с токенами."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Время жизни access токена в секундах")


class RefreshTokenRequest(BaseModel):
    """Схема запроса на обновление токена."""

    refresh_token: str = Field(..., description="Refresh токен")


# =============================================================================
# Схемы для роботов
# =============================================================================


class RobotBase(BaseModel):
    """Базовая схема робота."""

    name: str = Field(..., min_length=1, max_length=255, description="Имя робота")
    hostname: str = Field(..., min_length=1, max_length=255, description="Hostname устройства")
    ip_address: str | None = Field(None, max_length=45, description="IP-адрес")
    architecture: Architecture = Field(default=Architecture.ARM64, description="Архитектура")
    description: str | None = Field(None, description="Описание робота")


class RobotCreate(RobotBase):
    """Схема для создания робота (при привязке)."""

    pair_code: str = Field(
        ...,
        min_length=8,
        max_length=8,
        pattern=r"^[A-Z0-9]{8}$",
        description="8-значный код привязки",
    )


class RobotUpdate(BaseModel):
    """Схема для обновления робота."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: RobotStatus | None = None
    network_id: int | None = None


class RobotResponse(RobotBase):
    """Схема ответа с информацией о роботе."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RobotStatus
    owner_id: int | None = None
    network_id: int | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None


class RobotDetailResponse(RobotResponse):
    """Расширенная схема с дополнительной информацией."""

    influxdb_token: str | None = Field(None, description="Токен InfluxDB (только для API)")


class RobotListResponse(BaseModel):
    """Схема списка роботов."""

    robots: list[RobotResponse]
    total: int


# =============================================================================
# Схемы для привязки
# =============================================================================


class PairRequest(BaseModel):
    """Запрос на регистрацию робота (от агента)."""

    hostname: str = Field(..., min_length=1, max_length=255)
    name: str | None = Field(None, max_length=255)
    ip_address: str | None = Field(None, max_length=45)
    architecture: Architecture = Field(default=Architecture.ARM64)
    pair_code: str = Field(
        ...,
        min_length=8,
        max_length=8,
        pattern=r"^[A-Z0-9]{8}$",
        description="8-значный код привязки",
    )


class PairResponse(BaseModel):
    """Ответ на запрос привязки."""

    robot_id: int
    pair_code: str
    status: PairCodeStatus
    expires_at: datetime
    influxdb_token: str | None = Field(
        None, description="Токен InfluxDB (выдаётся после подтверждения)"
    )
    message: str


class PairConfirmRequest(BaseModel):
    """Запрос на подтверждение привязки (от пользователя)."""

    robot_name: str | None = Field(None, max_length=255, description="Новое имя робота")


class PairConfirmResponse(BaseModel):
    """Ответ на подтверждение привязки."""

    robot_id: int
    status: RobotStatus
    influxdb_token: str
    message: str


class PairCodeInfoResponse(BaseModel):
    """Информация о коде привязки."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    status: PairCodeStatus
    created_at: datetime
    expires_at: datetime
    robot: RobotResponse | None = None


class PairStatusResponse(BaseModel):
    """Статус привязки для polling агентом."""

    status: PairCodeStatus
    robot_id: int | None = None
    robot_token: str | None = Field(
        None, description="Токен для отправки метрик (только после подтверждения)"
    )
    api_url: str = Field(..., description="URL API для отправки метрик")
    message: str


# =============================================================================
# Общие схемы
# =============================================================================


class HealthResponse(BaseModel):
    """Схема ответа health check."""

    status: str = "ok"
    version: str
    database: str = "connected"
    metrics_backend: str = "heartbeat_only"


# =============================================================================
# Сети (ROS_DOMAIN_ID)
# =============================================================================


class NetworkCreate(BaseModel):
    """Создание сети."""

    name: str = Field(..., min_length=1, max_length=255)
    ros_domain_id: int = Field(..., ge=0, le=101)


class NetworkUpdate(BaseModel):
    """Обновление сети."""

    name: str | None = Field(None, min_length=1, max_length=255)


class NetworkResponse(BaseModel):
    """Сеть."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ros_domain_id: int
    owner_id: int
    created_at: datetime
    robot_count: int = Field(0, description="Число роботов пользователя в этой сети (админ — все роботы)")


# =============================================================================
# Workloads / оркестрация
# =============================================================================


class WorkloadCreateRequest(BaseModel):
    """Новый peer-под в кластере."""

    name: str = Field(..., min_length=1, max_length=255)
    workload_type: str = Field(default="compute_peer", max_length=64)
    architecture: Architecture = Field(default=Architecture.ARM64)
    network_id: int | None = Field(None, description="Сеть из каталога (ROS_DOMAIN_ID)")
    publish_topic: str = Field(default="/topic_a", max_length=512)
    subscribe_topic: str = Field(default="/topic_b", max_length=512)
    peer_shard: int = Field(default=1, ge=1)
    node_hostname: str | None = Field(None, max_length=253)


class WorkloadMigrateRequest(BaseModel):
    """Целевая нода (kubernetes.io/hostname)."""

    node_hostname: str | None = Field(None, max_length=253)


class WorkloadResponse(BaseModel):
    """Запись логического workload."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    network_id: int | None
    workload_type: str
    k8s_deployment_name: str
    desired_node_hostname: str | None
    status: WorkloadStatus
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Заготовленные compute-peer (пресеты)
# =============================================================================


class ComputePresetResponse(BaseModel):
    """Пресет для UI запуска peer."""

    id: str
    deployment_name: str
    display_name: str
    publish_topic: str
    subscribe_topic: str
    peer_shard: int
    memory_request_mib: int
    cpu_request_millicores: int


class ComputePresetLaunchRequest(BaseModel):
    """Целевая нода или автоматический выбор из пула worker/dev."""

    node_hostname: str | None = Field(None, max_length=253)
    auto_orchestrate: bool = Field(
        default=False,
        description="Автовыбор ноды: статический отсев + скоринг по запасу RAM/CPU",
    )

    @model_validator(mode="after")
    def node_or_auto(self) -> ComputePresetLaunchRequest:
        if self.auto_orchestrate:
            return self
        if not self.node_hostname or not str(self.node_hostname).strip():
            raise ValueError("Укажите ноду или включите автоматическую оркестрацию")
        return self


class ComputePresetLaunchResponse(BaseModel):
    """Результат запуска пресета на ноде."""

    ok: bool = True
    preset_id: str
    deployment_name: str
    node_hostname: str
    architecture: str
    image: str


# =============================================================================
# Логи rosout
# =============================================================================


class RosLogEntryResponse(BaseModel):
    """Строка лога."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    network_id: int | None
    ros_node_name: str | None
    level: str | None
    message: str
    recorded_at: datetime


class RosOutIngestItem(BaseModel):
    """Одно сообщение /rosout от bridge."""

    network_id: int | None = None
    ros_node_name: str | None = None
    level: str | None = None
    message: str


class RosOutIngestBatch(BaseModel):
    """Батч от rosout-bridge."""

    entries: list[RosOutIngestItem]


# =============================================================================
# Аккаунт (ссылки на Keycloak)
# =============================================================================


class AccountResponse(BaseModel):
    """Профиль + ссылки."""

    user: UserResponse
    keycloak_account_url: str
    networks: list[NetworkResponse] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Схема ошибки."""

    detail: str
    error_code: str | None = None
