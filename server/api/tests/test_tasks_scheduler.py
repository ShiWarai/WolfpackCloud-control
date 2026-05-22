"""Покрытие start_scheduler / stop_scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_start_scheduler_registers_job(monkeypatch):
    from app import tasks as tasks_mod

    sched = MagicMock(running=False)
    monkeypatch.setattr(tasks_mod, "scheduler", sched)
    tasks_mod.start_scheduler()
    sched.add_job.assert_called_once()
    sched.start.assert_called_once()


def test_stop_scheduler_when_running(monkeypatch):
    from app import tasks as tasks_mod

    sched = MagicMock(running=True)
    monkeypatch.setattr(tasks_mod, "scheduler", sched)
    tasks_mod.stop_scheduler()
    sched.shutdown.assert_called_once_with(wait=False)


def test_stop_scheduler_noop_when_not_running(monkeypatch):
    from app import tasks as tasks_mod

    sched = MagicMock(running=False)
    monkeypatch.setattr(tasks_mod, "scheduler", sched)
    tasks_mod.stop_scheduler()
    sched.shutdown.assert_not_called()
