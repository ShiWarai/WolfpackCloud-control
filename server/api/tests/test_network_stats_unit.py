"""robot_counts_by_network_ids."""

from __future__ import annotations

import pytest

from app.models import Network, Robot, RobotStatus, User, UserRole
from app.services.network_stats import robot_counts_by_network_ids


@pytest.mark.asyncio
async def test_robot_counts_empty_network_ids(db_session):
    admin = User(email="adm@t.l", name="A", role=UserRole.ADMIN, keycloak_sub="ksa")
    db_session.add(admin)
    await db_session.commit()
    assert await robot_counts_by_network_ids(db_session, admin, []) == {}


@pytest.mark.asyncio
async def test_robot_counts_admin_sees_all(db_session):
    admin = User(email="adm2@t.l", name="A", role=UserRole.ADMIN, keycloak_sub="ksa2")
    owner = User(email="ow@t.l", name="O", role=UserRole.USER, keycloak_sub="kso")
    db_session.add_all([admin, owner])
    await db_session.flush()
    net = Network(name="n1", ros_domain_id=101, owner_id=owner.id)
    db_session.add(net)
    await db_session.flush()
    robot = Robot(
        name="r1",
        hostname="h1",
        owner_id=owner.id,
        network_id=net.id,
        status=RobotStatus.ACTIVE,
    )
    db_session.add(robot)
    await db_session.commit()

    out = await robot_counts_by_network_ids(db_session, admin, [net.id])
    assert out[net.id] == 1


@pytest.mark.asyncio
async def test_robot_counts_user_only_own(db_session):
    owner = User(email="ow2@t.l", name="O", role=UserRole.USER, keycloak_sub="kso2")
    other = User(email="ot@t.l", name="X", role=UserRole.USER, keycloak_sub="ksx")
    db_session.add_all([owner, other])
    await db_session.flush()
    net = Network(name="n2", ros_domain_id=102, owner_id=owner.id)
    db_session.add(net)
    await db_session.flush()
    robot = Robot(
        name="r2",
        hostname="h2",
        owner_id=owner.id,
        network_id=net.id,
        status=RobotStatus.ACTIVE,
    )
    db_session.add(robot)
    await db_session.commit()

    out_owner = await robot_counts_by_network_ids(db_session, owner, [net.id])
    assert out_owner[net.id] == 1

    out_other = await robot_counts_by_network_ids(db_session, other, [net.id])
    assert out_other == {}
