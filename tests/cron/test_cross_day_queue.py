"""A provider claim queued across Tokyo midnight cannot launch a worker."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_provider_claim_then_cross_midnight(tmp_path, monkeypatch):
    from cron import jobs, scheduler
    from cron.scheduler_provider import InProcessCronScheduler
    from cron import executions

    monkeypatch.setattr(jobs, 'CRON_DIR', tmp_path)
    monkeypatch.setattr(jobs, 'JOBS_FILE', tmp_path / 'jobs.json')
    monkeypatch.setattr(executions, 'EXECUTIONS_FILE', tmp_path / 'executions.db')
    now = datetime(2026, 6, 1, 23, 59, tzinfo=ZoneInfo('Asia/Tokyo'))
    clock = [now]
    monkeypatch.setattr(jobs, '_hermes_now', lambda: clock[0])
    job = {'id': 'queue', 'name': 'queue', 'prompt': 'test',
           'schedule': {'kind': 'interval', 'minutes': 1440},
           'next_run_at': (now - timedelta(minutes=1)).isoformat(),
           'enabled': True, 'state': 'scheduled', 'skip_cross_day_catchup': True,
           'repeat': {'times': None, 'completed': 0}}
    jobs.save_jobs([job])
    provider = InProcessCronScheduler()
    claim = provider.claim_fire('queue')
    assert claim is not None
    clock[0] += timedelta(minutes=2)
    monkeypatch.setattr(scheduler, '_launch_external_cron_worker', lambda job: (_ for _ in ()).throw(AssertionError('worker launched')))
    assert provider.fire_claimed(claim)
    assert jobs.load_jobs()[0]['fire_claim'] is None
