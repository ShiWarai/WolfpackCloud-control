"""Покрытие tasks.mark_inactive_robots."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_mark_inactive_commits_when_robots_updated(monkeypatch):
    from app import tasks as tasks_mod

    class FakeSession:
        def __init__(self):
            self.committed = False

        async def execute(self, stmt):  # noqa: ARG002
            class R:
                def fetchall(self):
                    return [(1, "bot-a")]

            return R()

        async def commit(self):
            self.committed = True

    sess = FakeSession()

    class CM:
        async def __aenter__(self):
            return sess

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(tasks_mod, "async_session_factory", lambda: CM())
    await tasks_mod.mark_inactive_robots()
    assert sess.committed is True


@pytest.mark.asyncio
async def test_mark_inactive_no_commit_when_none(monkeypatch):
    from app import tasks as tasks_mod

    class FakeSession:
        def __init__(self):
            self.committed = False

        async def execute(self, stmt):  # noqa: ARG002
            class R:
                def fetchall(self):
                    return []

            return R()

        async def commit(self):
            self.committed = True

    sess = FakeSession()

    class CM:
        async def __aenter__(self):
            return sess

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(tasks_mod, "async_session_factory", lambda: CM())
    await tasks_mod.mark_inactive_robots()
    assert sess.committed is False
