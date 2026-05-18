"""
Конфигурация WolfpackCloud Control API.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
    )

    app_name: str = "WolfpackCloud Control API"
    debug: bool = False
    api_base_url: str = "http://localhost:8000"

    secret_key: str = "dev-secret-key-change-in-production"
    pair_code_expiration_minutes: int = 15

    database_url: str = "postgresql://wolfpack_control:wolfpack_control@localhost:5432/wolfpack_control"

    # Keycloak OIDC
    keycloak_issuer: str = "http://localhost:8080/realms/wolfpack-control"
    keycloak_jwks_url: str = (
        "http://localhost:8080/realms/wolfpack-control/protocol/openid-connect/certs"
    )
    keycloak_audience: str = "wolfpack-control-web"
    #: Client ID для OAuth2 в Swagger UI (вход через браузер). Должен быть публичный клиент realm,
    #: как у SPA — не bearer-only «api»-клиент. По умолчанию wolfpack-control-web.
    keycloak_swagger_client_id: str = "wolfpack-control-web"

    #: Через запятую: preferred_username или email — считать админом Control без роли admin в JWT (опционально)
    control_admin_usernames: str = ""

    # Kubernetes
    k8s_namespace: str = "wolfpackcloud-zenoh"
    k8s_worker_role_label: str = "wolfpack.io/role"
    #: Через запятую: какие значения wolfpack.io/role — пул оркестрации (worker + dev на одном уровне)
    k8s_resource_pool_role_values: str = "worker,dev"
    #: Не показывать master/control-plane ноды в «Ресурсах кластера»
    k8s_hide_control_plane_nodes: bool = True
    #: Значения wolfpack.io/role, которые никогда не в пуле UI (master и т.п.)
    k8s_orchestration_exclude_role_values: str = "master"
    #: Опционально: если нода без нужной wolfpack.io/role, но с этой парой label — считается в пуле (как dev-worker)
    k8s_pool_optional_label_key: str = ""
    k8s_pool_optional_label_value: str = ""
    k8s_managed_by_label: str = "wolfpack.io/managed-by"
    k8s_managed_by_value: str = "wolfpackcloud-control"

    compute_peer_image_amd64: str = (
        "10.43.50.10:5000/wolfpackcloud-compute-instance-peer:humble-amd64"
    )
    compute_peer_image_arm64: str = (
        "10.43.50.10:5000/wolfpackcloud-compute-instance-peer:humble-arm64"
    )

    rosout_ingest_token: str = "change-me-ingest-token"

    keycloak_account_base_url: str | None = None

    @property
    def control_admin_identities_lower(self) -> frozenset[str]:
        """Идентификаторы для повышения до admin (совпадение с preferred_username или email, без регистра)."""
        raw = (self.control_admin_usernames or "").strip()
        if not raw:
            return frozenset()
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())

    @property
    def orchestration_excluded_roles(self) -> frozenset[str]:
        raw = (self.k8s_orchestration_exclude_role_values or "").strip()
        if not raw:
            return frozenset()
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())

    @property
    def resource_pool_roles(self) -> frozenset[str]:
        """Значения метки k8s_worker_role_label для списка нод и scheduling compute-peer."""
        raw = (self.k8s_resource_pool_role_values or "").strip()
        if not raw:
            parts = {"worker", "dev"}
        else:
            parts = {x.strip().lower() for x in raw.split(",") if x.strip()}
        if not parts:
            parts = {"worker", "dev"}
        # master не должен попадать в affinity даже при опечатке в списке ролей
        return frozenset(parts - self.orchestration_excluded_roles)

    @property
    def pool_optional_label(self) -> tuple[str, str] | None:
        key = (self.k8s_pool_optional_label_key or "").strip()
        val = (self.k8s_pool_optional_label_value or "").strip()
        if key and val:
            return (key, val)
        return None

    @property
    def async_database_url(self) -> str:
        """URL для asyncpg."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def keycloak_account_console_url(self) -> str:
        """Ссылка на Account Console Keycloak."""
        if self.keycloak_account_base_url:
            return self.keycloak_account_base_url.rstrip("/")
        issuer = self.keycloak_issuer.rstrip("/")
        return f"{issuer}/account"


@lru_cache
def get_settings() -> Settings:
    """Закэшированные настройки."""
    return Settings()
