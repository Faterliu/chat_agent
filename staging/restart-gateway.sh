#!/bin/bash
# Restart the temporary test gateway as the hermes user.
#
# NOT the permanent service — systemd provisioning is Phase 16. This exists so the
# test instance can be bounced after a config change without fighting shell quoting.
#
# Why a script file: multi-line SSH command strings get mangled by the local shell
# wrapper (heredocs and nested quotes in particular). Files transfer intact.

set -u

LOG=/var/lib/hermes/gateway-test.log
REPO=/var/lib/hermes/.hermes/hermes-agent
PY=$REPO/venv/bin/python

# Use the INSTALLER'S LAUNCHER, not the repo's own ./hermes script.
# The repo file is a source entry point; running it picks up the system interpreter and
# dies with `ModuleNotFoundError: No module named 'dotenv'`. The launcher at
# ~/.local/bin/hermes explicitly execs the venv python:
#   exec "$REPO/venv/bin/python" "$REPO/hermes" "$@"
# This is exactly the failure the official install guide describes under
# "Non-Sudo / System Service User Installs" -> step 4.
LAUNCHER=/var/lib/hermes/.local/bin/hermes

echo "=== stop any running instance ==="
if pgrep -f "$PY.*hermes gateway run" > /dev/null 2>&1; then
  pkill -f "$PY.*hermes gateway run"
  echo "sent SIGTERM"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "$PY.*hermes gateway run" > /dev/null 2>&1 || break
    sleep 1
  done
  if pgrep -f "$PY.*hermes gateway run" > /dev/null 2>&1; then
    echo "still alive after 10s; forcing"
    pkill -9 -f "$PY.*hermes gateway run"
    sleep 2
  fi
  echo "stopped"
else
  echo "nothing was running"
fi

echo "=== start ==="
rm -f "$LOG"
cd /var/lib/hermes || exit 1

# The pypi mirror must be in the environment: Hermes lazily installs optional
# packages at runtime (observed: boto3) and would otherwise stall against pypi.org,
# which is unreachable from this host.
nohup env \
  UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
  UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  "$LAUNCHER" gateway run > "$LOG" 2>&1 &

echo "launched pid=$!"
sleep 25

echo "=== connection state ==="
grep -aiE "qqbot connected|Ready, session_id|Gateway running with|Connected" \
  /var/lib/hermes/.hermes/logs/agent.log 2>/dev/null | tail -6

echo "=== any fallback already? ==="
grep -aiE "Fallback activated|BadRequestError" /var/lib/hermes/.hermes/logs/agent.log 2>/dev/null | tail -3 \
  || echo "  none since start"
