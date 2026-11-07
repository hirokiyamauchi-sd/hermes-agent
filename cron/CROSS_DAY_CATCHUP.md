# Opt-in cross-day catch-up fence

`hermes cron create ... --skip-cross-day on` or `hermes cron edit ID --skip-cross-day on` enables the fence for one job. Use `--skip-cross-day off` to disable it. Absent on existing jobs means off.

An automatic occurrence is skipped when its actual scheduled instant falls on an earlier calendar date than worker launch in the job's pinned IANA timezone, or the profile timezone when unpinned. This applies even within a grace period and after time spent in the worker queue. Explicit manual/force fires have no scheduled occurrence and are not skipped. Other catch-up policies continue to apply independently.

The execution is cancelled before launching the worker; the already-advanced schedule is preserved, the owned fire claim released, and a missed-occurrence row is recorded. This is not a deployment instruction: update the candidate and restart only through the operator's normal procedure.

Automatic provider callbacks have no exact occurrence identity, so they are rejected for jobs with this option; they cannot safely distinguish duplicates or queued older slots. Use the built-in ticker for those jobs. Explicit manual and force runs remain available. Jobs without this option retain their existing provider behavior. This does not establish compatibility with external scheduler providers.
