"""
SQLAlchemy ORM модели для WolfpackCloud Control.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(enum.StrEnum):
    """Роли пользователей."""

    USER = "user"
    ADMIN = "admin"


class RobotStatus(enum.StrEnum):
    """Статусы робота."""

    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Architecture(enum.StrEnum):
    """Архитектура процессора."""

    ARM64 = "arm64"
    AMD64 = "amd64"
    ARMHF = "armhf"


class PairCodeStatus(enum.StrEnum):
    """Статусы кода привязки."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


class WorkloadStatus(enum.StrEnum):
    """Статус логического workload."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class User(Base):
    """Пользователь (синхронизируется из Keycloak по keycloak_sub)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keycloak_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.USER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    grafana_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superset_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    robots: Mapped[list["Robot"]] = relationship("Robot", back_populates="owner")
    networks: Mapped[list["Network"]] = relationship("Network", back_populates="owner")


class Network(Base):
    """Логическая ROS-сеть (DOMAIN_ID)."""

    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ros_domain_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="networks")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    robots: Mapped[list["Robot"]] = relationship("Robot", back_populates="network")


class Robot(Base):
    """Робот."""

    __tablename__ = "robots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    architecture: Mapped[Architecture] = mapped_column(
        Enum(Architecture, name="architecture", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=Architecture.ARM64,
    )
    status: Mapped[RobotStatus] = mapped_column(
        Enum(RobotStatus, name="robot_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RobotStatus.PENDING,
    )
    influxdb_token: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="SET NULL"))
    network: Mapped["Network | None"] = relationship("Network", back_populates="robots")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    owner: Mapped["User | None"] = relationship("User", back_populates="robots")

    pair_codes: Mapped[list["PairCode"]] = relationship(
        "PairCode", back_populates="robot", cascade="all, delete-orphan"
    )


class PairCode(Base):
    """Код привязки робота."""

    __tablename__ = "pair_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"), nullable=False)
    status: Mapped[PairCodeStatus] = mapped_column(
        Enum(
            PairCodeStatus, name="pair_code_status", values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
        default=PairCodeStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    robot: Mapped["Robot"] = relationship("Robot", back_populates="pair_codes")


class LogicalNode(Base):
    """Управляемый workload (Deployment в k8s)."""

    __tablename__ = "logical_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="SET NULL"))
    workload_type: Mapped[str] = mapped_column(String(64), nullable=False)
    k8s_deployment_name: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    desired_node_hostname: Mapped[str | None] = mapped_column(String(253))
    status: Mapped[WorkloadStatus] = mapped_column(
        Enum(
            WorkloadStatus,
            name="workload_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=WorkloadStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RosLogEntry(Base):
    """Кэш строк rosout для UI."""

    __tablename__ = "ros_log_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="SET NULL"))
    ros_node_name: Mapped[str | None] = mapped_column(String(512))
    level: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
