"""Юнит-тесты разборки JWT payload и decode при заглушенном JWKS."""

from __future__ import annotations

import jwt as pyjwt
import pytest

from app.config import get_settings
from app.services.keycloak_jwt import (
    decode_keycloak_access_token,
    effective_roles_from_payload,
    realm_roles_from_payload,
)


def test_realm_roles_from_payload_missing():
    assert realm_roles_from_payload({}) == []


def test_realm_roles_from_payload_reads_claim():
    p = {"realm_access": {"roles": ["offline_access", "admin"]}}
    assert realm_roles_from_payload(p) == ["offline_access", "admin"]


def test_effective_roles_merges_realm_and_client():
    p = {
        "realm_access": {"roles": ["default-role"]},
        "resource_access": {
            "wolfpack-control-web": {"roles": ["admin"]},
            "account": {"roles": ["manage-account"]},
        },
    }
    roles = effective_roles_from_payload(p)
    assert "default-role" in roles
    assert "admin" in roles
    assert "manage-account" in roles


def test_decode_roundtrip_rs256(make_access_token):
    settings = get_settings()
    token = make_access_token()
    payload = decode_keycloak_access_token(token, settings)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"


def test_decode_retries_when_audience_wrong(make_access_token):
    """Совпадает логика keycloak_jwt: второй decode без verify_aud."""
    settings = get_settings()
    token = make_access_token(audience="other-client")

    payload = decode_keycloak_access_token(token, settings)
    assert payload["sub"] == "user-1"


def test_decode_invalid_token_raises(make_access_token):
    settings = get_settings()
    token = make_access_token()
    corrupt = token.rsplit(".", 1)[0] + ".badsig"

    with pytest.raises(pyjwt.DecodeError):
        decode_keycloak_access_token(corrupt, settings)
