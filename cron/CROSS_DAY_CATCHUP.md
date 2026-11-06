# Per-job cross-day catch-up (candidate)

Recurring cron and interval jobs may opt in with the boolean job field
`skip_cross_day_catchup: true`; absent or false preserves existing behavior.
The jobs store API supports `update_job(job_id, {"skip_cross_day_catchup": True})`.
No CLI/dashboard control is included in this candidate. To limit the policy to
three jobs, explicitly update only those three records after separate approval.
This change itself does not update any jobs.

An automatic occurrence whose scheduled date is before the dispatch date in
`Asia/Tokyo` is skipped and the recurring schedule advances. Same-day late
runs remain subject to the existing global catch-up and other scheduler policies.
Manual run-now/force fires are exempt. One-shot jobs retain existing behavior.
A queued claim is checked again at worker launch. Skip decisions are logged;
queued skips are recorded as unsuccessful execution attempts, not job runs.
Third-party providers that override the built-in claim/dispatch methods must
implement this policy themselves; this candidate cannot enforce arbitrary custom
provider code. Existing in-flight external workers must run the new code for the
launch-time check to apply.
