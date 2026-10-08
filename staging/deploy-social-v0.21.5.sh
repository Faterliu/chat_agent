#!/usr/bin/env bash
# 仅首次部署主动关心增量；保留用户隔离、群回复和提醒补丁。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
patch=/var/lib/hermes/social-v0.21.5.patch
admin=/var/lib/hermes/social-admin.py
launcher=/var/lib/hermes/.local/bin/hermes
pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
backup="$home/backups/social-$(date -u +%Y%m%dT%H%M%SZ)"
pids() { pgrep -f "$pattern" || true; }
stop_gateway() {
    local pid
    pid="$(pids)"
    [[ -n "$pid" && "$pid" != *$'\n'* ]]
    kill -TERM "$pid"
    for _ in {1..45}; do [[ -z "$(pids)" ]] && return 0; sleep 1; done
    return 1
}
start_gateway() {
    [[ -z "$(pids)" ]]
    cd /var/lib/hermes
    nohup env HERMES_HOME="$home" \
        UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
        UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        "$launcher" gateway run >> "$backup/gateway.log" 2>&1 < /dev/null &
}
[[ "$(id -un)" == hermes ]]
[[ "$(git -C "$repo" rev-parse HEAD)" == f97608f178d1ffeca59860195ab7da295f7c8e5f ]]
[[ "$(sha256sum "$patch" | cut -d' ' -f1)" == 11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f ]]
[[ "$(pids | wc -l)" -eq 1 ]]
[[ ! -e "$home/social.pause" ]]
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
git -C "$repo" apply --check "$patch"
"$repo/venv/bin/python" "$admin" preflight
mkdir -m 700 "$backup"
cp -p "$home/config.yaml" "$backup/config.yaml"
cp -p "$home/.env" "$backup/environment-before"
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
[[ ! -e "$home/social.db" ]] || sqlite3 "$home/social.db" ".backup '$backup/social-before.db'"
[[ ! -f "$home/cron/jobs.json" ]] || cp -p "$home/cron/jobs.json" "$backup/jobs-before.json"
tar -C "$repo" -czf "$backup/source-before.tar.gz" \
    agent/inline_tool_executors.py gateway/run.py gateway/run_inbound.py \
    gateway/run_turn_runner.py toolsets.py hermes_cli/tools_config.py hermes_cli/toolset_scope.py gateway/platforms/qqbot/adapter.py \
    tools/qq_reminder.py tools/gateway_user_scope.py tools/tool_search.py
cp -p "$patch" "$backup/applied.patch"
chmod 600 "$backup"/*
printf 'backup=%s\n' "$backup"
stop_gateway
# 停机后再核查，避免在备份窗口出现未归属数据。
applied=false
rollback() {
    trap - ERR
    if [[ -n "$(pids)" ]]; then stop_gateway || { printf '%s\n' '无法停止网关，禁止重复启动'; exit 1; }; fi
    if $applied; then git -C "$repo" apply -R "$patch"; fi
    cp -p "$backup/config.yaml" "$home/config.yaml"
    # 保留 social.db、新会话和现有提醒，绝不恢复旧业务数据。
    start_gateway
    printf '%s\n' '主动关心检查失败；源码与配置已恢复，原网关已启动'
    exit 1
}
trap rollback ERR
"$repo/venv/bin/python" "$admin" preflight
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
git -C "$repo" apply "$patch"
applied=true
"$repo/venv/bin/python" "$admin" enable
"$repo/venv/bin/python" "$admin" seed
"$launcher" tools enable social --platform qqbot
"$launcher" tools enable social --platform weixin
offset="$(stat -c%s "$home/logs/agent.log")"
start_gateway
sleep 25
[[ "$(pids | wc -l)" -eq 1 ]]
tail -c "+$((offset + 1))" "$home/logs/agent.log" > "$backup/startup.log"
grep -aq 'qqbot connected' "$backup/startup.log"
grep -aq 'Connected account=' "$backup/startup.log"
if grep -aiqE 'Social.*unavailable|Social.*blocked|Traceback|session expired|weixin.*fatal' "$backup/startup.log"; then false; fi
git -C "$repo" apply -R --check "$patch"
"$repo/venv/bin/python" "$admin" verify
[[ "$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print t-a}' /proc/meminfo)" -lt 1363149 ]]
trap - ERR
printf 'social_gateway_pid=%s\n' "$(pids)"
printf '%s\n' '主动关心部署完成，QQ／微信已连接，原有提醒及群回复补丁保留'
free -m
