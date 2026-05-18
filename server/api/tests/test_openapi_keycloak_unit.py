"""Кастомизация OpenAPI для Keycloak Swagger."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.security import HTTPBearer

from app.openapi_keycloak import KEYCLOAK_OAUTH_SCHEME, patch_openapi_for_keycloak_swagger


def test_patch_openapi_adds_keycloak_oauth_scheme():
    app = FastAPI()
    bearer = HTTPBearer()

    @app.get("/secured")
    async def secured(_: str = Depends(bearer)):
        return {"ok": True}

    patch_openapi_for_keycloak_swagger(app, issuer="http://keycloak/realms/wolfpack")
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert KEYCLOAK_OAUTH_SCHEME in schemes
    assert "authorizationCode" in schemes[KEYCLOAK_OAUTH_SCHEME]["flows"]

    sec_blocks = schema["paths"]["/secured"]["get"]["security"]
    keys = [k for block in sec_blocks for k in block]
    assert KEYCLOAK_OAUTH_SCHEME in keys
