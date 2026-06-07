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

### Worked example: end-to-end maintenance (disable -> edit -> verify -> enable)

Goal: change only the cron schedule for an existing job while keeping everything else intact.

Example job:
- `id=<id>`

1) Snapshot + disable (so you never edit an active job)
```bash
id=<id>

openclaw cron show --json "$id" > /tmp/cron-${id}.before.json
openclaw cron disable "$id"
openclaw cron show --json "$id" > /tmp/cron-${id}.disabled.json
```

2) Edit the cron schedule (leave delivery/agent/session untouched)
```bash
# Example change: expr (update to your intended value)
openclaw cron edit "$id" \
  --cron "<new expr>" \
  --tz <IANA> \
  --exact
```

3) Verify config while still disabled (diff against before)
```bash
openclaw cron show --json "$id" > /tmp/cron-${id}.after-edit.json
openclaw cron status

# Compare the key fields operators should expect to remain stable:
jq -S '{
  agentId,
  enabled,
  sessionTarget,
  schedule: {kind, expr, tz},
  delivery: {mode, channel, to, bestEffort},
  payload: {toolsAllow: (.payload.toolsAllow // null)}
}' /tmp/cron-${id}.before.json > /tmp/cron-${id}.before.fields.json
jq -S '{
  agentId,
  enabled,
  sessionTarget,
  schedule: {kind, expr, tz},
  delivery: {mode, channel, to, bestEffort},
  payload: {toolsAllow: (.payload.toolsAllow // null)}
}' /tmp/cron-${id}.after-edit.json > /tmp/cron-${id}.after-edit.fields.json

diff -u /tmp/cron-${id}.before.fields.json /tmp/cron-${id}.after-edit.fields.json | head -n 200 || true
```

Minimum checklist:
- `enabled` is still `false` in `after-edit.json`
- `agentId`, `sessionTarget`, and `delivery` match `before.json`
- Only `schedule.expr` / `schedule.tz` changed (plus any incidental ordering)

4) Enable + confirm (still using `show --json` snapshots)
```bash
openclaw cron enable "$id"
openclaw cron show --json "$id" > /tmp/cron-${id}.after-enable.json

# Optional: confirm the job isn’t failing immediately
openclaw cron runs "$id"

# Quick sanity check (what you changed + that it’s enabled)
jq -S '{enabled, schedule, nextRunAtMs: .state.nextRunAtMs}' /tmp/cron-${id}.after-enable.json
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
- First, record whether this job was enabled before you started:
  ```bash
  wasEnabled=$(jq -r '.enabled' /tmp/cron-${id}.before.json)
  ```

- Then restore only the operator-relevant fields (schedule/agent/session/delivery) while keeping the job disabled.

Practical restore pattern (extract from the snapshot + re-apply via flags):
```bash
before=/tmp/cron-${id}.before.json

agentId=$(jq -r '.agentId' "$before")
sessionTarget=$(jq -r '.sessionTarget' "$before")
cronExpr=$(jq -r '.schedule.expr' "$before")
tz=$(jq -r '.schedule.tz' "$before")
channel=$(jq -r '.delivery.channel' "$before")
to=$(jq -r '.delivery.to' "$before")
bestEffort=$(jq -r '.delivery.bestEffort' "$before")

if [[ "$bestEffort" == "false" ]]; then
  openclaw cron edit "$id" \
    --agent "$agentId" \
    --session "$sessionTarget" \
    --cron "$cronExpr" \
    --tz "$tz" \
    --channel "$channel" \
    --to "$to" \
    --no-best-effort-deliver \
    --exact
else
  openclaw cron edit "$id" \
    --agent "$agentId" \
    --session "$sessionTarget" \
    --cron "$cronExpr" \
    --tz "$tz" \
    --channel "$channel" \
    --to "$to" \
    --best-effort-deliver \
    --exact
fi

# Optional: restore tool allow-list if it exists in the snapshot
toolsAllow=$(jq -r '.payload.toolsAllow // empty | join(",")' "$before")
if [[ -n "$toolsAllow" ]]; then
  openclaw cron edit "$id" --tools "$toolsAllow"
fi
```

Note: Don’t try to “re-import” raw JSON—**extract values and re-apply via `openclaw cron edit` flags** (field names/availability can vary across Gateway versions).

4) Validate restored config (compare specific fields from JSON snapshots)
```bash
openclaw cron show "$id"
openclaw cron show --json "$id" > /tmp/cron-${id}.after-rollback.json
openclaw cron status

# Compare only the operator-relevant fields you care about restoring.
jq -S '{
  agentId,
  enabled,
  sessionTarget,
  schedule: {kind, expr, tz},
  delivery: {mode, channel, to, bestEffort},
  payload: {toolsAllow: (.payload.toolsAllow // null)}
}' /tmp/cron-${id}.before.json > /tmp/cron-${id}.before.fields.json

jq -S '{
  agentId,
  enabled,
  sessionTarget,
  schedule: {kind, expr, tz},
  delivery: {mode, channel, to, bestEffort},
  payload: {toolsAllow: (.payload.toolsAllow // null)}
}' /tmp/cron-${id}.after-rollback.json > /tmp/cron-${id}.after-rollback.fields.json

diff -u /tmp/cron-${id}.before.fields.json /tmp/cron-${id}.after-rollback.fields.json | head -n 200 || true
```


5) Enable again (only if it was enabled before)
```bash
if [[ "$wasEnabled" == "true" ]]; then
  openclaw cron enable "$id"
else
  openclaw cron disable "$id"
fi
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
  - `openclaw cron show --json <id> | jq '.payload.toolsAllow // null'`
  - If `null`, the job likely isn’t configured with an allow-list (or the field isn’t present in that Gateway version).

8) Agent/workflow mismatch
- Symptom: agent returns errors or no-ops
- Check:
  - ensure the job is assigned to the intended agent id
  - inspect the job payload/message fields in `openclaw cron show --json <id>`

9) Wrong job ID (high impact)
- Failure: disabling/enabling the wrong job, or editing a similarly-shaped cron
- Quick checks:
  - Always run `openclaw cron show --json <id>` and sanity-check `name`, `agentId`, and `enabled` before disabling.
  - Keep the before snapshot file next to the ID so you don’t mix outputs.

Concrete example (safe pre-flight):
```bash
candidate=<id>
openclaw cron show --json "$candidate" | jq -S '{name,agentId,sessionTarget,enabled,schedule}'
# only proceed if this matches what you intended
```

If you see `enabled` or `agentId` doesn’t match, stop and re-check the ID from `openclaw cron list`.

10) Edited schedule vs enable flag (one changed, the other didn’t)
- Failure patterns:
  - You updated `--cron` but forgot to enable (job stays disabled).
  - You enabled the job but didn’t apply the intended schedule/agent/delivery edits.
- Quick checks:
  - After edits, verify `enabled` didn’t change unless you explicitly enabled:
    - `openclaw cron show --json <id> | jq -r '.enabled'`
  - Compare config snapshots:
    - `/tmp/cron-${id}.disabled.json` (should show `enabled: false`)
    - `/tmp/cron-${id}.after-enable.json` (should show `enabled: true`)

Concrete evidence patterns:
- "I edited, but it still won’t run":
  ```bash
  openclaw cron edit "$id" --cron '<expr>' --tz <IANA> --exact
  openclaw cron show --json "$id" | jq -r '.enabled'  # prints false
  ```
- "I enabled, but I didn’t actually apply edits":
  ```bash
  openclaw cron enable "$id"
  openclaw cron show --json "$id" | jq -S '{schedule,delivery,agentId,sessionTarget}'
  ```

11) Inconsistent/changed JSON fields across versions
- Failure: copying values from JSON fields that don’t exist (or moved) in the Gateway version you’re using
- Fix:
  - Extract only the specific values you need (cron/tz, agent, session, delivery destination) and re-apply using `openclaw cron edit` flags.
  - Don’t assume the JSON keys you saw yesterday still match today.

Concrete field-drift check (what actually exists right now):
```bash
openclaw cron show --json "$id" | jq -S '{schedule,delivery,sessionTarget,agentId,payload}'
```

Typical gotcha: some Gateway versions include `payload.toolsAllow`, others might omit it. For rollback/restore, always do:
```bash
before=/tmp/cron-${id}.before.json
cronExpr=$(jq -r '.schedule.expr' "$before")
tz=$(jq -r '.schedule.tz' "$before")
openclaw cron edit "$id" --cron "$cronExpr" --tz "$tz" --exact
```

(And similarly extract/restore agent/session/delivery from the snapshot.)

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

Concrete example:
```bash
# 1) Edit config (does not create a new run by itself)
openclaw cron edit "$id" --cron '<new expr>' --tz <IANA> --exact

# 2) Check config changed
openclaw cron show --json "$id" | jq -S '.schedule'

# 3) If you need to actually run now, force a one-off execution
openclaw cron run "$id"

# 4) Then inspect run history
openclaw cron runs "$id"

# 5) Finally, scheduler health is separate from run history
openclaw cron status
```

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
