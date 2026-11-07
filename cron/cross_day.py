"""Opt-in date fence for an automatic occurrence, checked immediately before launch."""
from datetime import datetime


def should_skip(job, now):
    if job.get("skip_cross_day") is not True:
        return False
    slot = job.get("_scheduled_instant")
    if not slot:
        return False  # manual/off-tick fire has no scheduled occurrence
    from cron.jobs_time import zone_for_job
    from cron.jobs import _ensure_aware
    try:
        due = _ensure_aware(datetime.fromisoformat(slot))
        zone = zone_for_job(job) or now.tzinfo
        return due.astimezone(zone).date() < now.astimezone(zone).date()
    except (ValueError, TypeError):
        return False


def settle_skipped(job):
    """Release only our own lease, retaining the already-advanced next occurrence."""
    from cron.jobs import _with_job, save_jobs, _complete_job_record
    from cron.executions import finish_execution, record_missed_occurrences
    claim = job.get("fire_claim") or {}
    owner = claim.get("by")

    def settle(jobs, _index, current):
        if not owner or (current.get("fire_claim") or {}).get("by") != owner:
            return False
        current.pop("fire_claim", None)
        current.pop("run_claim", None)
        # Fence repeated provider notifications after the lease is released.
        current["cross_day_skipped_at"] = job.get("_scheduled_instant")
        if (current.get("schedule") or {}).get("kind") == "once":
            _complete_job_record(current)
        save_jobs(jobs)
        return True

    released = _with_job(job["id"], settle, False)
    finish_execution(str(job["execution_id"]), success=False, cancelled=True,
                     error="Skipped: scheduled occurrence crossed the local date boundary")
    if released:
        record_missed_occurrences(str(job["id"]), count=1,
            first_instant=job.get("_scheduled_instant"), detail="skipped: cross-day catch-up disabled")
    return False
