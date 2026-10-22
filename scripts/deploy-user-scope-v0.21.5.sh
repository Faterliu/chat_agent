#!/usr/bin/env bash
# Apply the verified v0.21.5 user-scope patch to the single manual gateway.
set -euo pipefail
umask 077

repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
patch=/var/lib/hermes/user-scope-v0.21.5.patch
launcher=/var/lib/hermes/.local/bin/hermes
expected_commit=f97608f178d1ffeca59860195ab7da295f7c8e5f
expected_patch=db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d
gateway_pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
backup="$home/backups/user-scope-$(date -u +%Y%m%dT%H%M%SZ)"
log="/var/lib/hermes/gateway-user-scope-$(date -u +%Y%m%dT%H%M%SZ).log"
agent_log="$home/logs/agent.log"

gateway_pids() { pgrep -f "$gateway_pattern" || true; }
start_gateway() {
    cd /var/lib/hermes
    nohup env UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
        UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        "$launcher" gateway run >> "$log" 2>&1 < /dev/null &
    echo "gateway start requested"
}
stop_gateway() {
    local pid
    pid="$(gateway_pids)"
    [[ -n "$pid" && "$pid" != *$'\n'* ]] || { echo 'expected one gateway'; return 1; }
    kill -TERM "$pid"
    for _ in {1..20}; do
        [[ -z "$(gateway_pids)" ]] && return 0
        sleep 1
    done
    echo 'gateway did not stop within 20 seconds'
    return 1
}

[[ "$(id -un)" == hermes ]] || { echo 'wrong account'; exit 1; }
[[ "$(git -C "$repo" rev-parse HEAD)" == "$expected_commit" ]] || { echo 'wrong Hermes commit'; exit 1; }
[[ "$(sha256sum "$patch" | cut -d' ' -f1)" == "$expected_patch" ]] || { echo 'patch checksum mismatch'; exit 1; }
[[ "$(git -C "$repo" diff --name-only)" == 'gateway/platforms/qqbot/adapter.py' ]] || {
    echo 'unexpected live source changes'; exit 1;
}
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py" || {
    echo 'QQ passive-reply patch missing'; exit 1;
}
[[ "$(gateway_pids | wc -l)" -eq 1 ]] || { echo 'gateway count is not one'; exit 1; }
for file in "$home/memories/MEMORY.md" "$home/memories/USER.md"; do
    [[ ! -s "$file" ]] || { echo 'unowned global memory appeared; aborting'; exit 1; }
done
if [[ -d "$home/pending/memory" ]] && \
   [[ -n "$(find "$home/pending/memory" -maxdepth 1 -type f -name '*.json' -print -quit)" ]]; then
    echo 'unowned pending memory appeared; aborting'
    exit 1
fi
git -C "$repo" apply --check "$patch"

mkdir -p -m 700 "$backup"
cp -p "$home/config.yaml" "$backup/config.yaml"
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
tar -C "$repo" -czf "$backup/source-before.tar.gz" \
    agent/agent_init.py agent/inline_tool_executors.py \
    gateway/run_turn_runner.py gateway/slash_commands.py gateway/platforms/qqbot/adapter.py \
    hermes_cli/write_approval_commands.py hermes_state_search.py hermes_state_sessions.py \
    hermes_state_titles.py tools/memory_tool.py tools/memory_tool_store.py \
    tools/session_search_tool.py tools/write_approval.py
chmod 600 "$backup"/*
echo "backup=$backup"

stop_gateway
git -C "$repo" apply "$patch"
log_offset="$(stat -c%s "$agent_log" 2>/dev/null || echo 0)"
start_gateway
sleep 25
if [[ "$(stat -c%s "$agent_log" 2>/dev/null || echo 0)" -lt "$log_offset" ]]; then
    log_offset=0
fi
if [[ "$(gateway_pids | wc -l)" -ne 1 ]] || \
   ! tail -c "+$((log_offset + 1))" "$agent_log" | grep -aq 'qqbot connected' || \
   ! grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"; then
    echo 'post-start check failed; rolling back source and gateway'
    if [[ -n "$(gateway_pids)" ]]; then stop_gateway; fi
    if git -C "$repo" apply -R --check "$patch"; then
        git -C "$repo" apply -R "$patch"
    else
        tar -C "$repo" -xzf "$backup/source-before.tar.gz"
        rm -f -- "$repo/tools/gateway_user_scope.py" "$repo/tests/tools/test_gateway_user_scope.py"
    fi
    start_gateway
    sleep 25
    [[ "$(gateway_pids | wc -l)" -eq 1 ]] || { echo 'rollback gateway failed to start'; exit 1; }
    echo 'rolled back; inspect gateway log'
    exit 1
fi
echo 'single gateway running; QQ WebSocket connected; passive-reply patch present'
echo "gateway_log=$log"
