"""Юнит-тесты чистых k8s-хелперов без кластера."""

from __future__ import annotations

import pytest

from kubernetes import client

from app.config import Settings
from app.services.k8s import (
    normalize_incluster_bearer_auth,
    node_matches_orchestration_pool,
    sanitize_k8s_name,
)


@pytest.fixture
def pool_settings() -> Settings:
    return Settings(
        k8s_worker_role_label="wolfpack.io/role",
        k8s_resource_pool_role_values="worker,dev",
        k8s_hide_control_plane_nodes=True,
        k8s_orchestration_exclude_role_values="master",
        k8s_pool_optional_label_key="",
        k8s_pool_optional_label_value="",
    )


def test_sanitize_k8s_name_basic():
    assert sanitize_k8s_name("My_Workload! ") == "my-workload"
    assert sanitize_k8s_name("___") != ""
    assert len(sanitize_k8s_name("a" * 100, max_len=10)) == 10


def test_node_matches_pool_worker(pool_settings: Settings):
    labels = {"wolfpack.io/role": "worker"}
    assert node_matches_orchestration_pool(labels, pool_settings) is True


def test_node_matches_pool_via_optional_label(pool_settings: Settings):
    s = pool_settings.model_copy(
        update={"k8s_pool_optional_label_key": "spot", "k8s_pool_optional_label_value": "yes"}
    )
    labels = {"spot": "yes"}
    assert node_matches_orchestration_pool(labels, s) is True


def test_node_matches_pool_control_plane_hidden(pool_settings: Settings):
    labels = {
        "wolfpack.io/role": "worker",
        "node-role.kubernetes.io/control-plane": "",
    }
    assert node_matches_orchestration_pool(labels, pool_settings) is False


def test_master_role_excluded(pool_settings: Settings):
    labels = {"wolfpack.io/role": "master"}
    assert node_matches_orchestration_pool(labels, pool_settings) is False


def test_normalize_incluster_bearer_auth_lowercase_prefix():
    cfg = client.Configuration()
    cfg.api_key = {"authorization": "bearer test-token"}
    normalize_incluster_bearer_auth(cfg)
    assert cfg.api_key == {"BearerToken": "test-token"}
    assert cfg.api_key_prefix == {"BearerToken": "Bearer"}


def test_normalize_incluster_bearer_auth_already_prefixed():
    cfg = client.Configuration()
    cfg.api_key = {"BearerToken": "plain-token"}
    cfg.api_key_prefix = {"BearerToken": "Bearer"}
    normalize_incluster_bearer_auth(cfg)
    assert cfg.api_key == {"BearerToken": "plain-token"}
    assert cfg.api_key_prefix == {}


def test_normalize_incluster_bearer_auth_bearer_token_with_bearer_prefix():
    """kubernetes 36 in-cluster: BearerToken уже 'bearer <jwt>' — strip, prefix пустой."""
    cfg = client.Configuration()
    cfg.api_key = {"BearerToken": "bearer eyJ.test"}
    normalize_incluster_bearer_auth(cfg)
    assert cfg.api_key == {"BearerToken": "eyJ.test"}
    assert cfg.api_key_prefix == {}
