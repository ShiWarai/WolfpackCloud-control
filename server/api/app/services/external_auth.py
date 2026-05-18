"""
Сервис создания учёток в Grafana и Superset при регистрации пользователя.

При регистрации в WolfpackCloud автоматически создаёт учётки с теми же
логином/паролем и ролью Editor (Grafana) / Gamma (Superset).
"""

import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class ExternalAuthService:
    """Создание и удаление учёток в Grafana и Superset."""

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

    async def create_grafana_user(self, email: str, password: str, name: str) -> int | None:
        """
        Создаёт пользователя в Grafana с ролью Editor.

        Returns:
            ID пользователя в Grafana или None при ошибке.
        """
        url = f"{self._settings.grafana_url.rstrip('/')}/api/admin/users"
        auth = (
            self._settings.grafana_admin_user,
            self._settings.grafana_admin_password,
        )
        login = email.split("@")[0] if "@" in email else email

        payload = {
            "name": name,
            "email": email,
            "login": login,
            "password": password,
            "OrgId": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    auth=auth,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Grafana create user failed: %s %s",
                        resp.status_code,
                        resp.text,
                    )
                    return None

                data = resp.json()
                user_id = data.get("id")
                if not user_id:
                    logger.warning("Grafana response missing user id: %s", data)
                    return None

                await self._set_grafana_org_role(int(user_id), "Editor", auth)
                return int(user_id)

        except httpx.RequestError as e:
            logger.warning("Grafana request failed: %s", e)
            return None

    async def _set_grafana_org_role(self, user_id: int, role: str, auth: tuple[str, str]) -> bool:
        """Устанавливает роль пользователя в организации (org 1)."""
        url = f"{self._settings.grafana_url.rstrip('/')}/api/orgs/1/users/{user_id}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(
                    url,
                    json={"role": role},
                    auth=auth,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Grafana set role failed for user %s: %s %s",
                        user_id,
                        resp.status_code,
                        resp.text,
                    )
                    return False
                return True
        except httpx.RequestError as e:
            logger.warning("Grafana set role request failed: %s", e)
            return False

    async def create_superset_user(self, email: str, password: str, name: str) -> int | None:
        """
        Создаёт пользователя в Superset с ролью Gamma (Editor).

        Returns:
            ID пользователя в Superset или None при ошибке.
        """
        base = self._settings.superset_url.rstrip("/")
        username = email.replace("@", "_").replace(".", "_")  # уникальный username

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token = await self._get_superset_token(client, base)
                if not token:
                    return None

                csrf = await self._get_superset_csrf(client, base, token)
                if not csrf:
                    return None

                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-CSRFToken": csrf,
                    "Content-Type": "application/json",
                }

                gamma_role_id = await self._get_superset_gamma_role_id(client, base, token)

                payload = {
                    "username": username,
                    "email": email,
                    "password": password,
                    "first_name": name or username,
                    "last_name": "",
                    "roles": [gamma_role_id] if gamma_role_id else [4],
                    "active": True,
                }

                resp = await client.post(
                    f"{base}/api/v1/security/users/",
                    json=payload,
                    headers=headers,
                )

                if resp.status_code not in (200, 201):
                    logger.warning(
                        "Superset create user failed: %s %s",
                        resp.status_code,
                        resp.text,
                    )
                    return None

                data = resp.json()
                return data.get("id")

        except httpx.RequestError as e:
            logger.warning("Superset request failed: %s", e)
            return None

    async def _get_superset_token(self, client: httpx.AsyncClient, base: str) -> str | None:
        """Получает JWT токен Superset."""
        resp = await client.post(
            f"{base}/api/v1/security/login",
            json={
                "username": self._settings.superset_admin_username,
                "password": self._settings.superset_admin_password,
                "provider": "db",
            },
        )
        if resp.status_code != 200:
            logger.warning("Superset login failed: %s %s", resp.status_code, resp.text)
            return None
        return resp.json().get("access_token")

    async def _get_superset_csrf(
        self, client: httpx.AsyncClient, base: str, token: str
    ) -> str | None:
        """Получает CSRF токен Superset."""
        client.headers["Authorization"] = f"Bearer {token}"
        resp = await client.get(f"{base}/api/v1/security/csrf_token/")
        if resp.status_code != 200:
            logger.warning("Superset CSRF failed: %s %s", resp.status_code, resp.text)
            return None
        return resp.json().get("result")

    async def _get_superset_gamma_role_id(
        self, client: httpx.AsyncClient, base: str, token: str
    ) -> int | None:
        """Получает ID роли Gamma в Superset."""
        client.headers["Authorization"] = f"Bearer {token}"
        resp = await client.get(f"{base}/api/v1/security/roles/")
        if resp.status_code != 200:
            return None
        for role in resp.json().get("result", []):
            if role.get("name") == "Gamma":
                return role.get("id")
        return None

    async def delete_grafana_user(self, user_id: int) -> bool:
        """Удаляет пользователя из Grafana."""
        url = f"{self._settings.grafana_url.rstrip('/')}/api/admin/users/{user_id}"
        auth = (
            self._settings.grafana_admin_user,
            self._settings.grafana_admin_password,
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, auth=auth)
                return resp.status_code in (200, 404)
        except httpx.RequestError as e:
            logger.warning("Grafana delete user failed: %s", e)
            return False

    async def delete_superset_user(self, user_id: int) -> bool:
        """Удаляет пользователя из Superset."""
        base = self._settings.superset_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token = await self._get_superset_token(client, base)
                if not token:
                    return False
                client.headers["Authorization"] = f"Bearer {token}"
                resp = await client.delete(f"{base}/api/v1/security/users/{user_id}")
                return resp.status_code in (200, 204, 404)
        except httpx.RequestError as e:
            logger.warning("Superset delete user failed: %s", e)
            return False
