"""CRUD-роутеры: robots, networks, pairing, account, events, internal, logs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.models import Network, PairCode, PairCodeStatus, Robot, RobotStatus, User, UserRole
from app.services.influx import InfluxError


@pytest.fixture
def influx_settings() -> Settings:
    return Settings(
        influxdb_url="http://influx.test:8086",
        influxdb_token="test-token",
        influxdb_org="wolfpackcloud_influxdb",
    )


async def _seed_user(db_session, *, sub: str, email: str, role: UserRole = UserRole.USER) -> User:
    user = User(email=email, keycloak_sub=sub, name=email.split("@")[0], role=role)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_account_returns_user_and_networks(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="acc-sub", email="acc@test.local")
    net = Network(name="net-a", ros_domain_id=42, owner_id=user.id)
    db_session.add(net)
    await db_session.commit()

    token = make_access_token(sub="acc-sub", email="acc@test.local")
    r = await async_client.get("/api/account", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "acc@test.local"
    assert len(body["networks"]) == 1
    assert body["networks"][0]["robot_count"] == 0


@pytest.mark.asyncio
async def test_networks_crud(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="net-sub", email="net@test.local")
    await db_session.commit()

    token = make_access_token(sub="net-sub", email="net@test.local")
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        "/api/networks",
        headers=headers,
        json={"name": "ros-net", "ros_domain_id": 7},
    )
    assert r.status_code == 201
    net_id = r.json()["id"]

    r = await async_client.get("/api/networks", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["robot_count"] == 0

    r = await async_client.patch(
        f"/api/networks/{net_id}",
        headers=headers,
        json={"name": "renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "renamed"

    r = await async_client.delete(f"/api/networks/{net_id}", headers=headers)
    assert r.status_code == 204

    r = await async_client.get("/api/networks", headers=headers)
    assert r.json() == []


@pytest.mark.asyncio
async def test_networks_duplicate_domain_id(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="dup-sub", email="dup@test.local")
    db_session.add(Network(name="first", ros_domain_id=99, owner_id=user.id))
    await db_session.commit()

    token = make_access_token(sub="dup-sub", email="dup@test.local")
    r = await async_client.post(
        "/api/networks",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "second", "ros_domain_id": 99},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_networks_forbidden_for_other_user(async_client, make_access_token, db_session):
    owner = await _seed_user(db_session, sub="own-net", email="own-net@test.local")
    other = await _seed_user(db_session, sub="oth-net", email="oth-net@test.local")
    net = Network(name="private", ros_domain_id=11, owner_id=owner.id)
    db_session.add(net)
    await db_session.commit()

    token = make_access_token(sub="oth-net", email="oth-net@test.local")
    r = await async_client.patch(
        f"/api/networks/{net.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "hack"},
    )
    assert r.status_code == 403
    assert other.id != owner.id


@pytest.mark.asyncio
async def test_robots_list_get_update_delete_heartbeat(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="rb-sub", email="rb@test.local")
    robot = Robot(
        name="alpha",
        hostname="alpha-host",
        owner_id=user.id,
        status=RobotStatus.INACTIVE,
    )
    db_session.add(robot)
    await db_session.commit()

    token = make_access_token(sub="rb-sub", email="rb@test.local")
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.get("/api/robots", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["robots"][0]["name"] == "alpha"

    r = await async_client.get("/api/robots?search=alpha", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1

    rid = robot.id
    r = await async_client.get(f"/api/robots/{rid}", headers=headers)
    assert r.status_code == 200

    r = await async_client.patch(
        f"/api/robots/{rid}",
        headers=headers,
        json={"name": "alpha-renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "alpha-renamed"

    r = await async_client.post(f"/api/robots/{rid}/heartbeat", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = await async_client.delete(f"/api/robots/{rid}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_robots_access_denied_for_other_user(async_client, make_access_token, db_session):
    owner = await _seed_user(db_session, sub="rb-own", email="rb-own@test.local")
    other = await _seed_user(db_session, sub="rb-oth", email="rb-oth@test.local")
    robot = Robot(name="secret", hostname="h", owner_id=owner.id, status=RobotStatus.ACTIVE)
    db_session.add(robot)
    await db_session.commit()

    token = make_access_token(sub="rb-oth", email="rb-oth@test.local")
    r = await async_client.get(
        f"/api/robots/{robot.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert other.id != owner.id


@pytest.mark.asyncio
async def test_robots_admin_sees_all(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="rb-adm", email="rb-adm@test.local")
    db_session.add(Robot(name="x", hostname="hx", owner_id=user.id, status=RobotStatus.ACTIVE))
    await db_session.commit()

    token = make_access_token(
        sub="admin-sub",
        email="admin@test.local",
        realm_roles=["admin"],
    )
    r = await async_client.get("/api/robots", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_pairing_register_confirm_and_status(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="pair-sub", email="pair@test.local")
    await db_session.commit()

    r = await async_client.post(
        "/api/pair",
        json={"pair_code": "ABCD1234", "hostname": "robot-1", "name": "R1"},
    )
    assert r.status_code == 201
    assert r.json()["pair_code"] == "ABCD1234"

    r = await async_client.get("/api/pair/abcd1234")
    assert r.status_code == 200
    assert r.json()["code"] == "ABCD1234"

    token = make_access_token(sub="pair-sub", email="pair@test.local")
    r = await async_client.post(
        "/api/pair/abcd1234/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"robot_name": "My Robot"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["influxdb_token"]

    r = await async_client.get("/api/pair/abcd1234/status")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["robot_token"] is not None
    assert user.id is not None


@pytest.mark.asyncio
async def test_pairing_duplicate_code_conflict(async_client, db_session):
    robot = Robot(name="pending", hostname="h", status=RobotStatus.PENDING)
    db_session.add(robot)
    await db_session.flush()
    db_session.add(
        PairCode(
            code="DUPCODE1",
            robot_id=robot.id,
            status=PairCodeStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await db_session.commit()

    r = await async_client.post(
        "/api/pair",
        json={"pair_code": "DUPCODE1", "hostname": "other"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_pairing_expired_code(async_client, db_session):
    robot = Robot(name="exp", hostname="h", status=RobotStatus.PENDING)
    db_session.add(robot)
    await db_session.flush()
    db_session.add(
        PairCode(
            code="EXPIRED1",
            robot_id=robot.id,
            status=PairCodeStatus.PENDING,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    r = await async_client.get("/api/pair/EXPIRED1/status")
    assert r.status_code == 200
    assert r.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_logs_status_connected(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.logs as logs_router

    monkeypatch.setattr(logs_router, "settings", influx_settings)

    async def fake_ping(settings):  # noqa: ARG001
        return True

    monkeypatch.setattr(logs_router, "influx_ping", fake_ping)
    monkeypatch.setattr(
        logs_router.k8s_svc,
        "get_rosout_bridge_status",
        lambda settings: "running",  # noqa: ARG005
    )

    token = make_access_token(sub="ls2", email="ls2@test.local")
    r = await async_client.get("/api/logs/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["influxdb"] == "connected"
    assert body["rosout_bridge"] == "running"
    assert body["message"] is None


@pytest.mark.asyncio
async def test_logs_list_success(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.logs as logs_router

    monkeypatch.setattr(logs_router, "settings", influx_settings)
    fake_rows = [
        {
            "id": 1,
            "network_id": 1,
            "ros_node_name": "/n",
            "level": "INFO",
            "message": "hi",
            "recorded_at": datetime.now(timezone.utc),
        }
    ]
    with patch(
        "app.routers.logs.ros_logs_store.list_ros_logs",
        new_callable=AsyncMock,
        return_value=fake_rows,
    ):
        token = make_access_token(sub="lg2", email="lg2@test.local")
        r = await async_client.get("/api/logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()[0]["message"] == "hi"


@pytest.mark.asyncio
async def test_logs_list_influx_error(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.logs as logs_router

    monkeypatch.setattr(logs_router, "settings", influx_settings)
    with patch(
        "app.routers.logs.ros_logs_store.list_ros_logs",
        new_callable=AsyncMock,
        side_effect=InfluxError("down"),
    ):
        token = make_access_token(sub="lg3", email="lg3@test.local")
        r = await async_client.get("/api/logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_events_list_success(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.events as events_router

    monkeypatch.setattr(events_router, "settings", influx_settings)
    fake_rows = [
        {
            "id": 1,
            "deployment": "dep-a",
            "from_host": "w1",
            "to_host": "w2",
            "status": "success",
            "user_id": 1,
            "preset_id": None,
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "finished_at": None,
        }
    ]
    with patch(
        "app.routers.events.deployment_events_store.list_deployment_events",
        new_callable=AsyncMock,
        return_value=fake_rows,
    ):
        token = make_access_token(sub="ev1", email="ev1@test.local")
        r = await async_client.get(
            "/api/events/deployments?deployment=dep-a&status=success",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    assert r.json()[0]["deployment"] == "dep-a"


@pytest.mark.asyncio
async def test_events_list_not_configured(async_client, make_access_token):
    token = make_access_token(sub="ev2", email="ev2@test.local")
    r = await async_client.get("/api/events/deployments", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_internal_ingest_requires_token(async_client):
    r = await async_client.post(
        "/api/internal/rosout",
        json={"entries": []},
        headers={"X-Ingest-Token": "wrong"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_internal_ingest_batch(async_client, monkeypatch, influx_settings):
    import app.routers.internal as internal_router

    monkeypatch.setattr(internal_router, "settings", influx_settings)
    with patch(
        "app.routers.internal.ros_logs_store.write_ros_logs",
        new_callable=AsyncMock,
    ) as mock_write:
        r = await async_client.post(
            "/api/internal/rosout",
            json={
                "entries": [
                    {
                        "network_id": 1,
                        "ros_node_name": "/n",
                        "level": "INFO",
                        "message": "m",
                    }
                ]
            },
            headers={"X-Ingest-Token": "change-me-ingest-token"},
        )
    assert r.status_code == 204
    mock_write.assert_awaited_once()


@pytest.mark.asyncio
async def test_robots_not_found_and_update_network(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="rb-nf", email="rb-nf@test.local")
    net = Network(name="n", ros_domain_id=55, owner_id=user.id)
    db_session.add(net)
    robot = Robot(name="b", hostname="h", owner_id=user.id, status=RobotStatus.ACTIVE)
    db_session.add(robot)
    await db_session.commit()

    token = make_access_token(sub="rb-nf", email="rb-nf@test.local")
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.get("/api/robots/99999", headers=headers)
    assert r.status_code == 404

    r = await async_client.patch(
        f"/api/robots/{robot.id}",
        headers=headers,
        json={"network_id": net.id},
    )
    assert r.status_code == 200
    assert r.json()["network_id"] == net.id


@pytest.mark.asyncio
async def test_robots_update_unknown_network(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="rb-un", email="rb-un@test.local")
    robot = Robot(name="b", hostname="h", owner_id=user.id, status=RobotStatus.ACTIVE)
    db_session.add(robot)
    await db_session.commit()

    token = make_access_token(sub="rb-un", email="rb-un@test.local")
    r = await async_client.patch(
        f"/api/robots/{robot.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"network_id": 99999},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_networks_not_found(async_client, make_access_token, db_session):
    await _seed_user(db_session, sub="net-nf", email="net-nf@test.local")
    await db_session.commit()

    token = make_access_token(sub="net-nf", email="net-nf@test.local")
    r = await async_client.patch(
        "/api/networks/99999",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_account_admin_sees_all_networks(async_client, make_access_token, db_session):
    user = await _seed_user(db_session, sub="acc-adm-own", email="acc-adm-own@test.local")
    db_session.add(Network(name="owned", ros_domain_id=88, owner_id=user.id))
    await db_session.commit()

    token = make_access_token(
        sub="admin-acc",
        email="admin-acc@test.local",
        realm_roles=["admin"],
    )
    r = await async_client.get("/api/account", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()["networks"]) >= 1


@pytest.mark.asyncio
async def test_logs_status_error_paths(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.logs as logs_router

    monkeypatch.setattr(logs_router, "settings", influx_settings)

    async def fake_ping(settings):  # noqa: ARG001
        return False

    monkeypatch.setattr(logs_router, "influx_ping", fake_ping)
    monkeypatch.setattr(
        logs_router.k8s_svc,
        "get_rosout_bridge_status",
        lambda settings: (_ for _ in ()).throw(RuntimeError("k8s down")),  # noqa: ARG005
    )

    token = make_access_token(sub="ls3", email="ls3@test.local")
    r = await async_client.get("/api/logs/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["influxdb"] == "error"
    assert body["rosout_bridge"] == "unknown"
    assert body["message"] is not None


@pytest.mark.asyncio
async def test_events_influx_error(async_client, make_access_token, monkeypatch, influx_settings):
    import app.routers.events as events_router

    monkeypatch.setattr(events_router, "settings", influx_settings)
    with patch(
        "app.routers.events.deployment_events_store.list_deployment_events",
        new_callable=AsyncMock,
        side_effect=InfluxError("down"),
    ):
        token = make_access_token(sub="ev3", email="ev3@test.local")
        r = await async_client.get("/api/events/deployments", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_internal_ingest_no_influx(async_client):
    r = await async_client.post(
        "/api/internal/rosout/one",
        json={"network_id": 1, "ros_node_name": "/n", "level": "INFO", "message": "m"},
        headers={"X-Ingest-Token": "change-me-ingest-token"},
    )
    assert r.status_code == 503


def test_can_access_robot_admin():
    from app.models import Robot, User, UserRole
    from app.routers.robots import can_access_robot

    admin = User(email="a@t", name="A", role=UserRole.ADMIN, keycloak_sub="adm")
    owner = User(email="o@t", name="O", role=UserRole.USER, keycloak_sub="own")
    owner.id = 1
    robot = Robot(name="r", hostname="h", owner_id=99, status=RobotStatus.ACTIVE)
    assert can_access_robot(robot, admin) is True
    assert can_access_robot(robot, owner) is False


@pytest.mark.asyncio
async def test_internal_ingest_one(async_client, monkeypatch, influx_settings):
    import app.routers.internal as internal_router

    monkeypatch.setattr(internal_router, "settings", influx_settings)
    with patch(
        "app.routers.internal.ros_logs_store.write_ros_logs",
        new_callable=AsyncMock,
    ) as mock_write:
        r = await async_client.post(
            "/api/internal/rosout/one",
            json={"network_id": 1, "ros_node_name": "/n", "level": "WARN", "message": "x"},
            headers={"X-Ingest-Token": "change-me-ingest-token"},
        )
    assert r.status_code == 204
    mock_write.assert_awaited_once()
