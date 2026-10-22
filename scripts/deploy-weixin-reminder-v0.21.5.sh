#!/usr/bin/env bash
# 在已部署 QQ 提醒的固定版本上，启用微信本人私聊一次性提醒。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
patch=/var/lib/hermes/weixin-reminder-v0.21.5.patch
launcher=/var/lib/hermes/.local/bin/hermes
pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
backup="$home/backups/weixin-reminder-$(date -u +%Y%m%dT%H%M%SZ)"
pids() { pgrep -f "$pattern" || true; }
stop_gateway() {
    local pid
    pid="$(pids)"
    [[ -n "$pid" && "$pid" != *$'\n'* ]]
    kill -TERM "$pid"
    for _ in {1..30}; do [[ -z "$(pids)" ]] && return 0; sleep 1; done
    return 1
}
start_gateway() {
    cd /var/lib/hermes
    nohup env HERMES_HOME="$home" \
        UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
        UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
        "$launcher" gateway run >> "$backup/gateway.log" 2>&1 < /dev/null &
}
[[ "$(id -un)" == hermes ]]
[[ "$(git -C "$repo" rev-parse HEAD)" == f97608f178d1ffeca59860195ab7da295f7c8e5f ]]
[[ "$(sha256sum "$patch" | cut -d' ' -f1)" == 49c2d49b5319fffb1a3a0954f54f030b374587f338c0c2033731a0811277161e ]]
[[ "$(pids | wc -l)" -eq 1 ]]
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
[[ -f "$repo/tools/gateway_user_scope.py" ]]
git -C "$repo" apply --check "$patch"
for name in USER.md MEMORY.md; do
    [[ ! -f "$home/memories/$name" ]] || [[ ! -s "$home/memories/$name" ]]
done
mkdir -p -m 700 "$backup"
cp -p "$home/config.yaml" "$backup/config.yaml"
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
tar -C "$repo" -czf "$backup/source-before.tar.gz" \
    tools/qq_reminder.py tools/cronjob_tools.py tests/tools/test_qq_reminder.py \
    gateway/platforms/qqbot/adapter.py tools/gateway_user_scope.py
[[ ! -f "$home/cron/jobs.json" ]] || cp -p "$home/cron/jobs.json" "$backup/jobs-before.json"
chmod 600 "$backup"/*
printf 'backup=%s\n' "$backup"
stop_gateway
applied=false
rollback() {
    trap - ERR
    if [[ -n "$(pids)" ]]; then stop_gateway || { printf '%s\n' '无法停止网关，不启动重复实例'; exit 1; }; fi
    if $applied; then git -C "$repo" apply -R "$patch"; fi
    cp -p "$backup/config.yaml" "$home/config.yaml"
    start_gateway
    printf '%s\n' '微信提醒检查失败，源码与配置已回滚，原网关已启动'
    exit 1
}
trap rollback ERR
git -C "$repo" apply "$patch"
applied=true
"$launcher" tools enable cronjob --platform weixin
offset="$(stat -c%s "$home/logs/agent.log")"
start_gateway
sleep 25
[[ "$(pids | wc -l)" -eq 1 ]]
tail -c "+$((offset + 1))" "$home/logs/agent.log" > "$backup/startup.log"
grep -aq 'qqbot connected' "$backup/startup.log"
grep -aq 'Connected account=' "$backup/startup.log"
if grep -aiqE 'session expired|weixin.*fatal|weixin.*startup failed' "$backup/startup.log"; then false; fi
git -C "$repo" apply -R --check "$patch"
trap - ERR
printf '%s\n' 'QQ和微信均已连接，受限提醒已启用'
"$launcher" tools list --platform weixin
free -m
