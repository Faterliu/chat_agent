#!/usr/bin/env bash
# 扫码配置完成后重启单个网关，失败则恢复扫码前配置。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
launcher=/var/lib/hermes/.local/bin/hermes
backup=${1:?需要传入本次扫码备份目录}
[[ "$backup" =~ ^/var/lib/hermes/\.hermes/backups/weixin-[0-9]{8}T[0-9]{6}Z$ ]]
[[ -f "$backup/.env" && -f "$backup/config.yaml" ]]
[[ "$(id -un)" == hermes ]]
[[ "$(git -C "$repo" rev-parse HEAD)" == f97608f178d1ffeca59860195ab7da295f7c8e5f ]]
pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
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
[[ "$(pids | wc -l)" -eq 1 ]]
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
[[ -f "$repo/tools/gateway_user_scope.py" && -f "$repo/tools/qq_reminder.py" ]]
cd "$repo"
"$repo/venv/bin/python" -c 'from dotenv import dotenv_values; from gateway.platforms.weixin import check_weixin_requirements; e=dotenv_values("/var/lib/hermes/.hermes/.env"); assert check_weixin_requirements(); assert e.get("WEIXIN_TOKEN") and e.get("WEIXIN_ACCOUNT_ID") and e.get("WEIXIN_ALLOWED_USERS"); assert e.get("WEIXIN_DM_POLICY")=="allowlist" and e.get("WEIXIN_GROUP_POLICY")=="disabled"'
cp -p "$repo/gateway/platforms/qqbot/adapter.py" "$backup/qqbot-adapter.py"
cp -p "$repo/tools/gateway_user_scope.py" "$backup/gateway_user_scope.py"
cp -p "$repo/tools/qq_reminder.py" "$backup/qq_reminder.py"
offset="$(stat -c%s "$home/logs/agent.log")"
stop_gateway
rollback() {
    trap - ERR
    if [[ -n "$(pids)" ]]; then stop_gateway || { printf '%s\n' '无法停止网关，未启动重复实例'; exit 1; }; fi
    cp -p "$backup/.env" "$home/.env"
    start_gateway
    printf '%s\n' '微信启动检查失败，已恢复扫码前环境并启动原网关'
    exit 1
}
trap rollback ERR
start_gateway
sleep 25
[[ "$(pids | wc -l)" -eq 1 ]]
tail -c "+$((offset + 1))" "$home/logs/agent.log" > "$backup/startup.log"
grep -aq 'qqbot connected' "$backup/startup.log"
grep -aq 'Connected account=' "$backup/startup.log"
if grep -aiqE 'session expired|weixin.*fatal|weixin.*startup failed' "$backup/startup.log"; then false; fi
trap - ERR
printf '%s\n' '单个网关已连接 QQ 和微信；仍需真实私聊验收'
"$launcher" tools list --platform weixin
free -m
