"""Расширение OpenAPI: OAuth2 authorization code для Swagger UI (Keycloak OIDC).

См. FastAPI: swagger_ui_init_oauth, swagger_ui_oauth2_redirect_url и кастомизацию openapi.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

KEYCLOAK_OAUTH_SCHEME = "KeycloakOIDC"
SCOPE_NAMES = ["openid", "profile", "email"]


def patch_openapi_for_keycloak_swagger(app: FastAPI, *, issuer: str) -> None:
    """Добавляет securityScheme oauth2 и дублирует security у операций с HTTP Bearer."""

    issuer_base = issuer.rstrip("/")
    authorization_url = f"{issuer_base}/protocol/openid-connect/auth"
    token_url = f"{issuer_base}/protocol/openid-connect/token"

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )

        openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            KEYCLOAK_OAUTH_SCHEME
        ] = {
            "type": "oauth2",
            "description": (
                "Авторизация через Keycloak (authorization code + PKCE в Swagger UI). "
                "Токен уходит в запросах как Bearer — совместимо с проверкой JWT API.\n\n"
                "**Важно:** в поле **client_id** всегда **`wolfpack-control-web`** (публичный клиент приложения в realm). "
                "**Не подставляйте сюда логин пользователя** — имя и пароль вводятся позже на странице Keycloak после редиректа. "
                "**client_secret** оставьте пустым. Если в **client_id** указать логин (например wolfpack-operator), "
                "Keycloak ответит «Client not found»."
            ),
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": authorization_url,
                    "tokenUrl": token_url,
                    "scopes": {
                        "openid": "OpenID",
                        "profile": "Профиль",
                        "email": "Email",
                    },
                }
            },
        }

        for path_item in (openapi_schema.get("paths") or {}).values():
            if not isinstance(path_item, dict):
                continue
            for _method, operation in path_item.items():
                if _method.startswith("x-") or not isinstance(operation, dict):
                    continue
                sec = operation.get("security")
                if not sec:
                    continue
                has_bearer = False
                has_kc = False
                for block in sec:
                    if not isinstance(block, dict):
                        continue
                    if KEYCLOAK_OAUTH_SCHEME in block:
                        has_kc = True
                    if any(k == "HTTPBearer" or k.endswith("Bearer") for k in block):
                        has_bearer = True
                if has_bearer and not has_kc:
                    sec.append({KEYCLOAK_OAUTH_SCHEME: SCOPE_NAMES})

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
