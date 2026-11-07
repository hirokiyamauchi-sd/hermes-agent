"""Isolated execution-path tests: no real workers, transports or production home."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

JST = ZoneInfo("Asia/Tokyo")


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError("network is forbidden in this test")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    from cron import jobs, scheduler
    now = [datetime(2026, 11, 8, 0, 1, tzinfo=JST)]
    monkeypatch.setattr(jobs, "_hermes_now", lambda: now[0])
    monkeypatch.setattr(scheduler, "_hermes_now", lambda: now[0])
    launches = []
    monkeypatch.setattr(scheduler, "_launch_external_cron_worker", lambda j: launches.append(j) or True)
    return jobs, scheduler, now, launches


def job_at(jobs, slot, *, enabled=True, zone="Asia/Tokyo"):
    job = jobs.create_job("test", "0 23 * * *", timezone=zone, skip_cross_day=enabled)
    jobs.update_job(job["id"], {"next_run_at": slot})
    return job


def builtin_fire(jobs, scheduler):
    from cron.executions import create_execution
    due = jobs.get_due_jobs()
    jobs.advance_next_runs([j["id"] for j in due])
    for job in due:
        job["execution_id"] = create_execution(job["id"], source="builtin")["id"]
        scheduler._process_due_job(job, None, None, False)
    return due


def test_provider_cross_day(setup):
    from cron.scheduler_provider import InProcessCronScheduler
    from cron.executions import list_executions
    jobs, scheduler, now, launches = setup
    job = job_at(jobs, "2026-11-07T23:00:00+09:00")
    InProcessCronScheduler().fire_due(job["id"])
    assert launches == []
    current = jobs.get_job(job["id"])
    assert not current.get("fire_claim")
    assert current["next_run_at"] == "2026-11-07T23:00:00+09:00"
    builtin_fire(jobs, scheduler)
    assert jobs.get_job(job["id"])["next_run_at"] > now[0].isoformat()
    assert any(x["status"] == "missed" for x in list_executions(job_id=job["id"]))


@pytest.mark.parametrize("slot,enabled,manual", [
    ("2026-11-07T23:00:00+09:00", False, False),

    ("2026-11-07T23:00:00+09:00", True, True),
])
def test_provider_allowed(setup, slot, enabled, manual):
    from cron.scheduler_provider import InProcessCronScheduler
    jobs, scheduler, now, launches = setup
    job = job_at(jobs, slot, enabled=enabled)
    InProcessCronScheduler().fire_due(job["id"], manual=manual)
    assert len(launches) == 1


def test_queued_builtin_after_midnight(setup):
    from cron.executions import create_execution
    jobs, scheduler, now, launches = setup
    now[0] = datetime(2026, 11, 7, 23, 30, tzinfo=JST)
    job = job_at(jobs, "2026-11-07T23:00:00+09:00")
    due = jobs.get_due_jobs()
    assert len(due) == 1
    jobs.advance_next_runs([job["id"]])
    due[0]["execution_id"] = create_execution(job["id"], source="builtin")["id"]
    now[0] = datetime(2026, 11, 8, 0, 1, tzinfo=JST)
    scheduler._process_due_job(due[0], None, None, False)
    assert launches == []
    assert not jobs.get_job(job["id"]).get("fire_claim")


def test_provider_cannot_steal_queued_builtin_occurrence(setup):
    from cron.executions import create_execution
    from cron.scheduler_provider import InProcessCronScheduler
    jobs, scheduler, now, launches = setup
    now[0] = datetime(2026, 11, 7, 23, 30, tzinfo=JST)
    job = job_at(jobs, "2026-11-07T23:00:00+09:00")
    due = jobs.get_due_jobs()
    jobs.advance_next_runs([job["id"]])
    due[0]["execution_id"] = create_execution(job["id"], source="builtin")["id"]
    now[0] = datetime(2026, 11, 8, 0, 1, tzinfo=JST)
    next_slot = jobs.get_job(job["id"])["next_run_at"]
    assert not InProcessCronScheduler().fire_due(job["id"])
    assert jobs.get_job(job["id"])["next_run_at"] == next_slot
    scheduler._process_due_job(due[0], None, None, False)
    assert not launches
    assert not jobs.get_job(job["id"]).get("fire_claim")


def test_builtin_same_day_launch(setup):
    jobs, scheduler, now, launches = setup
    now[0] = datetime(2026, 11, 8, 23, 1, tzinfo=JST)
    job_at(jobs, "2026-11-08T23:00:00+09:00")
    assert len(builtin_fire(jobs, scheduler)) == 1
    assert len(launches) == 1


def test_default_off_and_job_timezone(setup):
    from cron.cross_day import should_skip
    jobs, scheduler, now, launches = setup
    job = jobs.create_job("test", "0 23 * * *")
    assert "skip_cross_day" not in job
    job.update(_scheduled_instant="2026-11-07T14:00:00+00:00")
    assert not should_skip(job, now[0])
    job.update(skip_cross_day=True, timezone="America/Los_Angeles")
    assert not should_skip(job, now[0])  # still Nov 7 in Los Angeles
    job["timezone"] = "Asia/Tokyo"
    assert should_skip(job, now[0])


def test_cli_round_trip(setup):
    import argparse
    from hermes_cli.subcommands.cron import build_cron_parser
    from hermes_cli.cron import _job_api_kwargs
    parser = argparse.ArgumentParser()
    build_cron_parser(parser.add_subparsers(), cmd_cron=lambda args: None)
    for verb, value, expected in [("create", "on", True), ("edit", "off", False)]:
        args = parser.parse_args(["cron", verb, "0 23 * * *" if verb == "create" else "jobid",
                                  "--skip-cross-day", value])
        assert _job_api_kwargs(args)["skip_cross_day"] is expected


def test_tool_create_edit_persist(setup):
    import json
    from tools.cronjob_tools import cronjob
    jobs, _, _, _ = setup
    result = json.loads(cronjob(action="create", schedule="0 23 * * *", prompt="test",
                                skip_cross_day=True))
    assert result["success"], result
    jid = result["job_id"]
    assert jobs.get_job(jid)["skip_cross_day"] is True
    result = json.loads(cronjob(action="update", job_id=jid, skip_cross_day=False))
    assert result["success"], result
    assert jobs.get_job(jid)["skip_cross_day"] is False


def test_builtin_manual_after_midnight(setup):
    from cron.executions import create_execution
    jobs, scheduler, now, launches = setup
    job = job_at(jobs, "2026-11-07T23:00:00+09:00")
    jobs.trigger_job(job["id"])
    due = jobs.get_due_jobs()
    assert len(due) == 1 and due[0]["_scheduled_instant"] is None
    jobs.advance_next_runs([job["id"]])
    due[0]["execution_id"] = create_execution(job["id"], source="builtin")["id"]
    scheduler._process_due_job(due[0], None, None, False)
    assert len(launches) == 1


def test_duplicate_provider_notification_and_next_slot(setup):
    from cron.scheduler_provider import InProcessCronScheduler
    jobs, scheduler, now, launches = setup
    now[0] = datetime(2026, 11, 7, 23, 59, tzinfo=JST)
    job = jobs.create_job("test", "1m", timezone="Asia/Tokyo", skip_cross_day=True)
    jobs.update_job(job["id"], {"next_run_at": now[0].isoformat()})
    due = jobs.get_due_jobs()
    jobs.advance_next_runs([job["id"]])
    from cron.executions import create_execution
    due[0]["execution_id"] = create_execution(job["id"], source="builtin")["id"]
    now[0] = datetime(2026, 11, 8, 0, 0, 1, tzinfo=JST)
    scheduler._process_due_job(due[0], None, None, False)
    provider = InProcessCronScheduler()
    next_slot = jobs.get_job(job["id"])["next_run_at"]
    assert 0 < (datetime.fromisoformat(next_slot) - now[0]).total_seconds() <= 60
    provider.fire_due(job["id"])
    provider.fire_due(job["id"])
    assert not launches
    assert jobs.get_job(job["id"])["next_run_at"] == next_slot


@pytest.mark.parametrize("method", ["force", "manual", "trigger"])
def test_skipped_once_can_be_run_explicitly(setup, method):
    from cron.scheduler_provider import InProcessCronScheduler
    jobs, scheduler, now, launches = setup
    now[0] = datetime(2026, 11, 7, 22, 0, tzinfo=JST)
    job = jobs.create_job("test", "2026-11-07T23:00:00+09:00", timezone="Asia/Tokyo", skip_cross_day=True)
    now[0] = datetime(2026, 11, 7, 23, 0, tzinfo=JST)
    due = jobs.get_due_jobs()
    jobs.advance_next_runs([job["id"]])
    from cron.executions import create_execution
    due[0]["execution_id"] = create_execution(job["id"], source="builtin")["id"]
    now[0] = datetime(2026, 11, 8, 0, 1, tzinfo=JST)
    provider = InProcessCronScheduler()
    scheduler._process_due_job(due[0], None, None, False)
    assert jobs.get_job(job["id"])["state"] == "completed"
    if method == "trigger":
        jobs.trigger_job(job["id"])
        provider.fire_due(job["id"])
    else:
        provider.fire_due(job["id"], **{method: True})
    assert len(launches) == 1


def test_registered_tool_schema_and_handler(setup):
    import json
    from tools.cronjob_tools import CRONJOB_SCHEMA, _cronjob_handler
    jobs, _, _, _ = setup
    assert CRONJOB_SCHEMA["parameters"]["properties"]["skip_cross_day"]["type"] == "boolean"
    result = json.loads(_cronjob_handler({"action": "create", "schedule": "0 23 * * *", "prompt": "test", "skip_cross_day": True}))
    assert result["success"], result
    jid = result["job_id"]
    assert jobs.get_job(jid)["skip_cross_day"] is True
    result = json.loads(_cronjob_handler({"action": "update", "job_id": jid, "skip_cross_day": False}))
    assert result["success"], result
    assert jobs.get_job(jid)["skip_cross_day"] is False
