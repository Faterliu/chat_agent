#!/usr/bin/env bash
# 部署经过隔离测试的 QQ 私聊一次性提醒补丁。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
patch=/var/lib/hermes/qq-reminder-v0.21.5.patch
launcher=/var/lib/hermes/.local/bin/hermes
pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
backup="$home/backups/qq-reminder-$(date -u +%Y%m%dT%H%M%SZ)"
log="$backup/gateway.log"
pids() { pgrep -f "$pattern" || true; }
stop_gateway() {
    local pid
    pid="$(pids)"
    [[ -n "$pid" && "$pid" != *$'\n'* ]] || return 1
    kill -TERM "$pid"
    for _ in {1..20}; do [[ -z "$(pids)" ]] && return 0; sleep 1; done
    return 1
}
start_gateway() {
    cd /var/lib/hermes
    nohup env HERMES_HOME="$home" \
        UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
        UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        "$launcher" gateway run >> "$log" 2>&1 < /dev/null &
}
[[ "$(id -un)" == hermes ]]
[[ "$(git -C "$repo" rev-parse HEAD)" == f97608f178d1ffeca59860195ab7da295f7c8e5f ]]
[[ "$(sha256sum "$patch" | cut -d' ' -f1)" == a6963923d87472e1e2aed67ecc85e253c86a6505e5fe707296ca744f0b1f79ba ]]
[[ "$(pids | wc -l)" -eq 1 ]]
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
[[ -f "$repo/tools/gateway_user_scope.py" ]]
git -C "$repo" apply --check "$patch"
mkdir -p -m 700 "$backup"
cp -p "$home/config.yaml" "$backup/config.yaml"
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
tar -C "$repo" -czf "$backup/source-before.tar.gz" \
    agent/inline_tool_executors.py tools/cronjob_tools.py \
    gateway/platforms/qqbot/adapter.py tools/gateway_user_scope.py
[[ ! -f "$home/cron/jobs.json" ]] || cp -p "$home/cron/jobs.json" "$backup/jobs-before.json"
chmod 600 "$backup"/*
echo "backup=$backup"
stop_gateway
applied=false
rollback() {
    trap - ERR
    echo 'deployment failed; restoring reminder source and configuration'
    if [[ -n "$(pids)" ]]; then stop_gateway || { echo 'unable to stop gateway; no duplicate launched'; exit 1; }; fi
    if $applied; then
        git -C "$repo" apply -R "$patch"
    fi
    cp -p "$backup/config.yaml" "$home/config.yaml"
    start_gateway
    exit 1
}
trap rollback ERR
git -C "$repo" apply "$patch"
applied=true
"$launcher" tools enable cronjob --platform qqbot
"$launcher" config set cron.wrap_response false
"$launcher" config set cron.max_parallel_jobs 1
offset="$(stat -c%s "$home/logs/agent.log")"
start_gateway
sleep 25
[[ "$(pids | wc -l)" -eq 1 ]]
tail -c "+$((offset + 1))" "$home/logs/agent.log" | grep -aq 'qqbot connected'
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
trap - ERR
echo 'single gateway connected; restricted QQ reminder enabled'
"$launcher" tools list --platform qqbot
"$launcher" cron status
