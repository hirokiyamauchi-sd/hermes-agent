"""Exercise the operator CLI against an isolated real jobs store."""
import argparse
import json

import pytest

from hermes_cli.subcommands.cron import build_cron_parser


def test_edit_flags_store_real_boolean_and_preserve_other_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from cron import jobs
    from hermes_cli.cron import cron_edit
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr(jobs, "CRON_DIR", tmp_path / "cron")
    parser = argparse.ArgumentParser()
    build_cron_parser(parser.add_subparsers(dest="command"), cmd_cron=lambda _: None)
    one = jobs.create_job("first", "0 9 * * *", name="first")
    two = jobs.create_job("second", "0 10 * * *", name="second")
    args = parser.parse_args(["cron", "edit", one["id"], "--skip-cross-day-catchup"])
    assert cron_edit(args) == 0
    assert jobs.resolve_job_ref(one["id"])["skip_cross_day_catchup"] is True
    assert "skip_cross_day_catchup" not in jobs.resolve_job_ref(two["id"])
    args = parser.parse_args(["cron", "edit", one["id"], "--name", "changed"])
    assert cron_edit(args) == 0
    assert jobs.resolve_job_ref(one["id"])["skip_cross_day_catchup"] is True
    args = parser.parse_args(["cron", "edit", one["id"], "--allow-cross-day-catchup"])
    assert cron_edit(args) == 0
    assert jobs.resolve_job_ref(one["id"])["skip_cross_day_catchup"] is False
    with pytest.raises(SystemExit):
        parser.parse_args(["cron", "edit", one["id"], "--skip-cross-day-catchup", "--allow-cross-day-catchup"])
