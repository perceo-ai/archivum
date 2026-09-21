#!/usr/bin/env bash
# Deploy Archivum to perceo-control (VM 104 on jigserver).
#
# Run from a machine that can reach the Proxmox host. Every step is read-only
# until the explicit apply at the end, so you can run it with --check first and
# see exactly what would happen.
#
#   scripts/deploy-perceo-control.sh --check   # report state, change nothing
#   scripts/deploy-perceo-control.sh           # pull, rebuild, restart, verify
#
# Deliberately not run automatically: this restarts the stack that holds your
# vault, and a deploy you did not watch is a deploy you cannot roll back from
# quickly.

set -euo pipefail

PVE_HOST="${PVE_HOST:-jigserver}"
VMID="${ARCHIVUM_VMID:-104}"
APP_DIR="${ARCHIVUM_APP_DIR:-/opt/perceo/archivum}"
BRANCH="${ARCHIVUM_BRANCH:-main}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# `qm guest exec` returns JSON with the command's output nested inside it.
guest() {
  ssh "$PVE_HOST" "qm guest exec $VMID -- bash -lc $(printf '%q' "$1")" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")); sys.stderr.write(d.get("err-data","")); sys.exit(d.get("exitcode",0))'
}

echo "→ Proxmox host: $PVE_HOST, VM $VMID, app dir $APP_DIR, branch $BRANCH"

echo "→ Guest agent"
ssh "$PVE_HOST" "qm agent $VMID ping" >/dev/null && echo "  agent responding"

echo "→ Current state"
guest "cd $APP_DIR && git rev-parse --short HEAD && git status --porcelain | head"
guest "cd $APP_DIR && docker compose ps --format '{{.Service}} {{.Status}}'"

if [ "$CHECK_ONLY" = "1" ]; then
  echo "→ --check: stopping here, nothing changed."
  exit 0
fi

# Modified tracked files mean somebody edited in place. Stop rather than
# overwrite work that exists nowhere else.
#
# Untracked files are deliberately not a blocker. `git pull --ff-only` cannot
# touch them, and this VM *requires* one: docker-compose.override.yml binds the
# services to the LAN address the Cloudflare tunnel reaches them on, and exists
# nowhere but here. Counting it as "uncommitted changes" made every deploy to
# the one machine this script is named after abort.
if guest "cd $APP_DIR && git status --porcelain --untracked-files=no" | grep -q .; then
  echo "✗ The working tree on $VMID has modified tracked files. Resolve those first." >&2
  exit 1
fi

untracked=$(guest "cd $APP_DIR && git ls-files --others --exclude-standard" || true)
if [ -n "$untracked" ]; then
  echo "  untracked files kept as-is:"
  echo "$untracked" | sed 's/^/    /'
fi

echo "→ Pulling $BRANCH"
guest "cd $APP_DIR && git fetch --all --quiet && git checkout $BRANCH --quiet && git pull --ff-only"

# Deliberately not ./update.sh: that wrapper needs Node, which perceo-control
# does not have, so it exits before touching anything. Compose is what actually
# runs there.
echo "→ Rebuilding"
# `qm guest exec` has its own deadline and answers "timeout reached, returning
# pid" while the build carries on in the background. Taken as success, the
# restart below then ran against images that did not exist yet, left the old
# containers up, and the script still printed a tick. Start it detached on
# purpose and wait for the process to actually leave.
guest "cd $APP_DIR && nohup docker compose build backend frontend mcp > /tmp/archivum-build.log 2>&1 & echo started"
printf '  building'
for _ in $(seq 1 120); do
  if ! guest "pgrep -c -f 'docker-compose compose build' 2>/dev/null || echo 0" | grep -qv '^0$'; then
    break
  fi
  printf '.'
  sleep 15
done
echo
if guest "tail -5 /tmp/archivum-build.log" | grep -qiE "error|failed"; then
  echo "✗ Build reported an error. Last lines:" >&2
  guest "tail -20 /tmp/archivum-build.log" >&2
  exit 1
fi

echo "→ Restarting"
guest "cd $APP_DIR && docker compose up -d backend frontend mcp"

echo "→ Verifying"
guest "cd $APP_DIR && docker compose ps --format '{{.Service}} {{.Status}}'"
# Checked from inside the VM, not through the tunnel: scripted requests through
# Cloudflare trip the shared login rate limiter.
# Checked against the address the services are actually published on. The
# override on this VM binds the LAN address so the Cloudflare tunnel can reach
# them, so a loopback check failed here no matter how healthy the stack was.
api_host=$(guest "cd $APP_DIR && docker compose port backend 8000 2>/dev/null | head -1" | tr -d '\r\n')
api_host=${api_host:-127.0.0.1:8000}
echo "  api published on $api_host"
guest "curl -fsS -o /dev/null -w 'api %{http_code}\n' http://$api_host/api/system/health || echo 'api health check failed'"

# The deploy is only real if the running process answers on something this
# release added. A tick printed without checking is how the last one reported
# success while the old containers were still up.
deployed=$(guest "curl -s -o /dev/null -w '%{http_code}' http://$api_host/api/skills" | tr -d '\r\n')
if [ "$deployed" = "404" ]; then
  echo "✗ /api/skills still 404 — the running process predates this release." >&2
  guest "cd $APP_DIR && docker compose ps --format '{{.Service}} {{.Status}}'" >&2
  exit 1
fi
echo "  /api/skills answers $deployed (401 = present and requiring a device key)"

guest "cd $APP_DIR && docker compose logs --tail 10 backend | tail -10"

echo "✓ Deployed. Sign the CLIs in if you have not yet:"
echo "    ssh $PVE_HOST \"qm guest exec $VMID -- docker exec -it archivum-backend claude login\""
echo "    ssh $PVE_HOST \"qm guest exec $VMID -- docker exec -it archivum-codex codex login\""
