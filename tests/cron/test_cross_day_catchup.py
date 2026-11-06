"""Exercise real ticker and provider claim with isolated stores and mocked execution."""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

RUN = r'''
import sys
from pathlib import Path
from cron import scheduler
from cron.scheduler_provider import InProcessCronScheduler
home = Path(sys.argv[1]); mode = sys.argv[2]
def run(job, **kwargs):
    (home / 'ran').write_text(str(job.get('_scheduled_instant')))
    return True
scheduler.run_one_job = run
if mode == 'builtin':
    scheduler.tick(verbose=False, sync=True)
else:
    InProcessCronScheduler().fire_due('blog', manual=mode == 'manual')
'''

@pytest.mark.parametrize('mode', ['builtin', 'provider', 'manual'])
@pytest.mark.parametrize('enabled,age,should_run', [
    (True, 'previous', False), (True, 'same', True), (False, 'previous', True),
])
def test_dispatch(tmp_path, mode, enabled, age, should_run):
    now = datetime.now(ZoneInfo('Asia/Tokyo'))
    slot = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if age == 'previous':
        slot -= timedelta(days=1)
    job = {'id': 'blog', 'name': 'blog', 'prompt': '',
           'schedule': {'kind': 'interval', 'minutes': 1440},
           'next_run_at': slot.isoformat(), 'enabled': True, 'state': 'scheduled',
           'skip_cross_day_catchup': enabled, 'no_agent': True, 'deliver': 'local',
           'repeat': {'times': None, 'completed': 0}}
    directory = tmp_path / 'cron'
    directory.mkdir()
    store = directory / 'jobs.json'
    store.write_text(json.dumps({'jobs': [job]}))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('HERMES_', '_HERMES_')) and not k.endswith(('_API_KEY', '_TOKEN'))}
    env['HERMES_HOME'] = str(tmp_path)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, '-c', RUN, str(tmp_path), mode], env=env,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'ran').exists() == (should_run or mode == 'manual')
    if enabled and age == 'previous' and mode != 'manual':
        assert datetime.fromisoformat(json.loads(store.read_text())['jobs'][0]['next_run_at']) > now
