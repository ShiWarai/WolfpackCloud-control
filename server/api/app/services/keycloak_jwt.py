"""Декодирование JWT Keycloak (JWKS, RS256)."""

from __future__ import annotations

import logging

import jwt
from jwt import PyJWKClient

from app.config import Settings

logger = logging.getLogger(__name__)


def decode_keycloak_access_token(token: str, settings: Settings) -> dict:
    """Валидация access token Keycloak."""
    jwks_client = PyJWKClient(settings.keycloak_jwks_url)
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    common = {
        "algorithms": ["RS256"],
        "issuer": settings.keycloak_issuer,
    }

    try:
        return jwt.decode(
            token,
            signing_key.key,
            audience=settings.keycloak_audience,
            **common,
        )
    except jwt.InvalidAudienceError:
        logger.debug("JWT audience mismatch, retrying without aud verification")
        return jwt.decode(
            token,
            signing_key.key,
            options={"verify_aud": False},
            **common,
        )


def realm_roles_from_payload(payload: dict) -> list[str]:
    """Realm roles из claim realm_access."""
    ra = payload.get("realm_access")
    if not isinstance(ra, dict):
        return []
    roles = ra.get("roles")
    return list(roles) if isinstance(roles, list) else []


def effective_roles_from_payload(payload: dict) -> frozenset[str]:
    """
    Роли из токена Keycloak: realm + все client roles из resource_access.

    Часто роль admin назначают как client role у wolfpack-control-web — она не попадает в realm_access.
    """
    out = set(realm_roles_from_payload(payload))
    ra = payload.get("resource_access")
    if isinstance(ra, dict):
        for entry in ra.values():
            if isinstance(entry, dict):
                cr = entry.get("roles")
                if isinstance(cr, list):
                    out.update(cr)
    return frozenset(out)
