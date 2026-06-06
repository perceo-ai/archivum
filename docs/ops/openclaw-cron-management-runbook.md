# OpenClaw cron management runbook

## Purpose
Maintain and safely change scheduled jobs managed by the OpenClaw Gateway cron scheduler (`openclaw cron *`).

## What this runbook covers
- Add a cron job
- Modify a cron job (patch fields)
- Verify scheduler + the next run
- Roll back changes (including partial/failed edits)
- Common failure modes and quick checks

## Safety rules (read once, follow every time)
1) **Verify the job ID before you touch it**
- Use `openclaw cron show <id>` / `openclaw cron show --json <id>` to confirm you’re editing the intended job.

2) **Snapshot before editing**
- Capture `openclaw cron show --json <id>` to a file before any `edit`/`enable` steps.

3) **Stay disabled until after validation**
- Don’t re-enable until you’ve confirmed config + next run expectations.

4) **Know what “config” vs “history” means**
- `openclaw cron show` = config
- `openclaw cron runs` = history
- `openclaw cron status` = scheduler health
- `openclaw cron run` = force immediate run

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

## Modify a cron job (safe workflow)
### 1) Capture current config (for rollback)
Before changing anything, snapshot the current config:
```bash
id=<id>
openclaw cron show --json "$id" > /tmp/cron-${id}.before.json
```

Also confirm you’ve picked the right job:
- `openclaw cron show "$id"`
- and sanity-check key fields in the JSON output (at minimum: `name`, `agent`, `sessionTarget`/`session`, `enabled`, `cron/tz`, and delivery destination fields).

### 2) Disable before patching
```bash
openclaw cron disable "$id"
```
Then confirm it’s actually disabled:
```bash
openclaw cron show --json "$id" > /tmp/cron-${id}.disabled.json
```
(You’re looking for the JSON field that indicates the job is disabled / `enabled: false`.)

### 3) Apply edits
Use one or more `openclaw cron edit` commands.
- Examples:
```bash
openclaw cron edit "$id" --cron "<new expr>" --tz <IANA>
openclaw cron edit "$id" --agent wrench
openclaw cron edit "$id" --session isolated
openclaw cron edit "$id" --announce --to discord:channel:<DISCORD_CHANNEL_ID>
```

If you change delivery, schedule, and agent in one maintenance window, it’s OK to do multiple `edit` calls—**just re-verify the final config in `show --json` before enabling**.

### 4) Validate config + expected next run (while still disabled)
```bash
openclaw cron show --json "$id" > /tmp/cron-${id}.after-edit.json
openclaw cron status
```
Minimum checklist:
- Scheduler health looks OK (`openclaw cron status`)
- The job config matches intent (`openclaw cron show "$id"`)
- The next run time looks correct for timezone + cron

Then (optional but helpful):
```bash
diff -u /tmp/cron-${id}.before.json /tmp/cron-${id}.after-edit.json | head -n 200 || true
```

### 5) Re-enable only after validation
```bash
openclaw cron enable "$id"
openclaw cron show --json "$id" > /tmp/cron-${id}.after-enable.json
openclaw cron runs "$id"   # optional: confirm no immediate failures
```

## Rollback procedure (including partial/failed edits)
Rollback is easiest if you captured `openclaw cron show --json` output before the edit.

1) Disable the job (again)
```bash
openclaw cron disable "$id"
```

2) Confirm it’s disabled (so you don’t accidentally re-run mid-rollback)
```bash
openclaw cron show --json "$id" > /tmp/cron-${id}.rollback-disabled.json
```

3) Restore previous fields
- Re-apply the prior schedule/agent/session/delivery fields using `openclaw cron edit <id> ...`.
- Use `/tmp/cron-${id}.before.json` to restore the exact cron expression + timezone + delivery fields.

Practical tip:
- Don’t try to “re-import” JSON blindly—**prefer extracting the specific values you need** and passing them into `openclaw cron edit` flags (field names can vary by Gateway version).

4) Validate restored config
```bash
openclaw cron show "$id"
openclaw cron show --json "$id" > /tmp/cron-${id}.after-rollback.json
openclaw cron status
```

5) Enable again (only if you’re confident)
```bash
openclaw cron enable "$id"
```

If the job was failing due to delivery or tools allow-list, also check the immediate run history:
- `openclaw cron runs "$id"`

## Verify after edits (post-enable checklist)
Minimum checklist:
1) Scheduler health
- `openclaw cron status`

2) Job config matches intent
- `openclaw cron show <id>`

3) Next run time looks right (timezone + cron)
- `openclaw cron show <id>` (read `Next` / schedule-related fields)

4) Optional: run once in debug mode
- `openclaw cron run <id>`
- Then confirm result in `openclaw cron runs <id>`

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
  - `openclaw cron show --json <id>` for the exact cron `expr`

4) Stagger timing surprises
- Symptom: run timing varies within a window
- Fix: use `--exact` when adding/updating scheduling.

5) Wrong session target
- Symptom: job can’t access expected state/files
- Check:
  - `openclaw cron show --json <id>` for `sessionTarget` / `session`

6) Delivery routing issues
- Symptom: `lastDeliveryStatus` not delivered; failures when `bestEffort=false`
- Check:
  - `openclaw cron show --json <id>` (delivery mode/destination)
  - Verify the destination exists and the token/account has access

7) Tool allow-list too restrictive
- Symptom: job fails with "tool not allowed" errors
- Check:
  - `openclaw cron show --json <id>` (`toolsAllow`)

8) Agent/workflow mismatch
- Symptom: agent returns errors or no-ops
- Check:
  - ensure the job is assigned to the intended agent id
  - inspect the job payload/message fields in `openclaw cron show --json <id>`

9) Wrong job ID (high impact)
- Failure: disabling/enabling the wrong job, or editing a similarly-shaped cron
- Quick checks:
  - Always run `openclaw cron show --json <id>` and sanity-check `name` + `agent` + `enabled` before disabling.
  - Keep the before snapshot file next to the ID so you don’t mix outputs.

10) Edited schedule vs enable flag (one changed, the other didn’t)
- Failure patterns:
  - You updated `--cron` but forgot to enable (job stays disabled).
  - You enabled the job but didn’t apply the intended schedule/agent/delivery edits.
- Quick checks:
  - Compare `enabled` in:
    - `/tmp/cron-${id}.disabled.json` (should be false)
    - `/tmp/cron-${id}.after-enable.json` (should be true)
  - Confirm schedule/delivery in `openclaw cron show --json <id>` after edits but before enabling.

11) Inconsistent/changed JSON fields across versions
- Failure: copying values from JSON fields that don’t exist (or moved) in the Gateway version you’re using
- Fix:
  - Extract only the specific values you need (cron/tz, agent, session, delivery destination) and re-apply using `openclaw cron edit` flags.
  - Don’t assume the JSON keys you saw yesterday still match today.

12) Run vs runs/status confusion
- Failure:
  - expecting `openclaw cron runs <id>` to change just because you edited config
  - or expecting `openclaw cron run <id>` to persist like config
- Quick checks:
  - Use:
    - `openclaw cron show` for config
    - `openclaw cron runs` for history
    - `openclaw cron run` to force a one-off execution
    - `openclaw cron status` for scheduler health

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
