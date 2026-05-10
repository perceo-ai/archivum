# OpenClaw cron management runbook

## Purpose
Maintain and safely change scheduled jobs managed by the OpenClaw Gateway cron scheduler (`openclaw cron *`).

## What this runbook covers
- Add a cron job
- Modify a cron job (patch fields)
- Verify the scheduler + the next run
- Roll back changes
- Common failure modes and quick checks

## Prerequisites
1) Gateway + cron scheduler reachable from this machine
   - Quick check:
     - `openclaw gateway status`
     - `openclaw cron status`

2) Identify the job you’re editing
   - `openclaw cron list`
   - Then:
     - `openclaw cron show <id>` (human) or `openclaw cron show --json <id>` (exact fields)

## Quick reference: commands
- List jobs: `openclaw cron list`
- Show job: `openclaw cron show <id>` or `openclaw cron show --json <id>`
- Add job: `openclaw cron add --help`
- Edit job: `openclaw cron edit <id> --help`
- Enable/disable: `openclaw cron enable <id>` / `openclaw cron disable <id>`
- Remove job: `openclaw cron rm <id>`
- Run immediately (debug): `openclaw cron run <id>`
- Run history: `openclaw cron runs <id>`
- Scheduler health: `openclaw cron status`

## Create / add a cron job
Example (mirrors the existing "Build queue sweep" job pattern):

1) Choose fields
- `--name` : job name
- `--agent` : agent id to run (e.g. `wrench`)
- `--session` : `main` or `isolated`
- `--cron` : cron expression (5-field or 6-field with seconds, depending on your usage)
- `--tz` : IANA timezone for the expression (e.g. `America/Los_Angeles`)
- Delivery: either `--announce` (chat text) and/or `--to` for explicit destination

2) Add
```bash
openclaw cron add \
  --name "<job name>" \
  --agent wrench \
  --session isolated \
  --cron "30 */1 * * *" \
  --tz America/Los_Angeles \
  --announce \
  --to discord:channel:<DISCORD_CHANNEL_ID> \
  --exact
```

Notes:
- `--exact` disables cron staggering (so the job fires at the expected time rather than within a stagger window).
- If you want the scheduler to only run when you wake it, use a disabled job first (`--disabled`) then enable later.

## Modify a cron job (patch fields)
**Before changing anything, capture the current config** so rollback is straightforward:
```bash
openclaw cron show --json <id> > /tmp/cron-<id>.json
```

### Typical edits
- Update schedule:
```bash
openclaw cron edit <id> --cron "<new expr>" --tz <IANA>
```
- Update agent:
```bash
openclaw cron edit <id> --agent wrench
```
- Update session target:
```bash
openclaw cron edit <id> --session isolated
```
- Update delivery destination:
```bash
openclaw cron edit <id> --announce --to discord:channel:<DISCORD_CHANNEL_ID>
```

### Safe workflow
1) Disable job (prevents accidental concurrent runs while patching)
```bash
openclaw cron disable <id>
```
2) Patch the job
3) Verify:
```bash
openclaw cron show <id>
openclaw cron runs <id>
openclaw cron status
```
4) Enable job
```bash
openclaw cron enable <id>
```

## Verify after edits
Minimum checklist:
1) Scheduler health
- `openclaw cron status`

2) Job config matches intent
- `openclaw cron show <id>`

3) The next run time looks right (timezone + cron)
- `openclaw cron show <id> | grep -E "next:|schedule:|status:"` (or just read the `Next` field from `openclaw cron list`)

4) (Optional) Run once in debug mode
- `openclaw cron run <id>`
- Then confirm result in `openclaw cron runs <id>`

## Rollback procedure
Rollback is easiest if you captured `openclaw cron show --json` output before the edit.

1) Disable the job
```bash
openclaw cron disable <id>
```

2) Restore previous fields
- Re-apply the prior schedule/agent/session/delivery fields using `openclaw cron edit <id> ...`
- Use the JSON snapshot to ensure the exact cron expression + timezone + delivery fields are restored.

3) Validate
```bash
openclaw cron show <id>
openclaw cron status
```

4) Enable again
```bash
openclaw cron enable <id>
```

If the job was failing due to delivery or tools allow-list, also check the immediate run history:
- `openclaw cron runs <id>`

## Common failure modes (and quick checks)
1) Gateway not reachable / scheduler unhealthy
- Symptom: jobs never start or show repeated errors
- Check:
  - `openclaw gateway status`
  - `openclaw cron status`

2) Timezone mismatch
- Symptom: "Next" time is unexpectedly early/late
- Check:
  - `openclaw cron show <id>` (look for `tz`)

3) Cron expression mistakes
- Symptom: job runs too often/too rarely
- Check:
  - `openclaw cron show --json <id>` for the exact `expr`

4) Stagger timing surprises
- Symptom: run timing varies within a window
- Fix: use `--exact` when adding/updating scheduling.

5) Wrong session target
- Symptom: job can’t access expected state/files
- Check:
  - `openclaw cron show <id>` for `sessionTarget`

6) Delivery routing issues
- Symptom: `lastDeliveryStatus` not delivered; failures when `bestEffort=false`
- Check:
  - `openclaw cron show --json <id>` (delivery mode/to/channel)
  - Verify the destination exists and the token/account has access

7) Tool allow-list too restrictive
- Symptom: job fails with "tool not allowed" errors
- Check:
  - `openclaw cron show --json <id>` (`toolsAllow`)

8) Agent/workflow mismatch
- Symptom: agent returns errors or no-ops
- Check:
  - job payload content (message)
  - ensure the job is assigned to the intended agent id

## Worked example: diagnosing an actively running job
1) Identify job:
- `openclaw cron list`

2) Inspect config:
- `openclaw cron show --json <id>`

3) Confirm it last ran successfully:
- Look for `lastRunStatus` and `lastDeliveryStatus` in the JSON

4) If you need to force a run:
- `openclaw cron run <id>`
- Then inspect:
  - `openclaw cron runs <id>`
