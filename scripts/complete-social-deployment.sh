#!/usr/bin/env bash
# 将本次初始增量替换为含 CLI 工具目录的完整增量；仅适用于指定初始备份。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
home=/var/lib/hermes/.hermes
old="$home/backups/social-catalog-20261008T020955Z/applied.patch"
patch=/var/lib/hermes/social-v0.21.5.patch
launcher=/var/lib/hermes/.local/bin/hermes
backup="$home/backups/social-catalog-$(date -u +%Y%m%dT%H%M%SZ)"
pattern='^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
pids() { pgrep -f "$pattern" || true; }
stop_gateway() {
    local pid="$(pids)"
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
[[ "$(pids | wc -l)" -eq 1 ]]
[[ "$(sha256sum "$old" | cut -d' ' -f1)" == 9c2c69b7837a048a18a88bcb77459aa2c1ebc267f5603e61831ec7006369c2dd ]]
[[ "$(sha256sum "$patch" | cut -d' ' -f1)" == 11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f ]]
git -C "$repo" apply -R --check "$old"
mkdir -m 700 "$backup"
cp -p "$home/config.yaml" "$backup/config.yaml"
sqlite3 "$home/state.db" ".backup '$backup/state.db'"
sqlite3 "$home/social.db" ".backup '$backup/social.db'"
tar -C "$repo" -czf "$backup/source-before.tar.gz" \
    hermes_cli/tools_config.py hermes_cli/toolset_scope.py agent/inline_tool_executors.py \
    gateway/run.py gateway/run_inbound.py gateway/run_turn_runner.py gateway/social_runtime.py \
    toolsets.py tools/tool_search.py tools/social_store.py tools/social_tool.py tests/tools/test_social.py
cp -p "$patch" "$backup/applied.patch"
chmod 600 "$backup"/*
printf 'backup=%s\n' "$backup"
stop_gateway
removed=false
applied=false
rollback() {
    trap - ERR
    if [[ -n "$(pids)" ]]; then stop_gateway || exit 1; fi
    if $applied; then git -C "$repo" apply -R "$patch"; fi
    if $removed; then git -C "$repo" apply "$old"; fi
    cp -p "$backup/config.yaml" "$home/config.yaml"
    start_gateway
    printf '%s\n' '工具目录检查失败，已恢复调整前源码与配置'
    exit 1
}
trap rollback ERR
git -C "$repo" apply -R "$old"
removed=true
git -C "$repo" apply --check "$patch"
git -C "$repo" apply "$patch"
applied=true
"$launcher" tools enable social --platform qqbot
"$launcher" tools enable social --platform weixin
"$repo/venv/bin/python" /var/lib/hermes/social-admin.py verify
offset="$(stat -c%s "$home/logs/agent.log")"
start_gateway
sleep 25
[[ "$(pids | wc -l)" -eq 1 ]]
tail -c "+$((offset + 1))" "$home/logs/agent.log" > "$backup/startup.log"
grep -aq 'qqbot connected' "$backup/startup.log"
grep -aq 'Connected account=' "$backup/startup.log"
if grep -aiqE 'Social.*unavailable|Social.*blocked|Traceback|session expired|weixin.*fatal' "$backup/startup.log"; then false; fi
git -C "$repo" apply -R --check "$patch"
grep -q '\[LOCAL PATCH\] QQ group messages must be PASSIVE replies' "$repo/gateway/platforms/qqbot/adapter.py"
trap - ERR
printf 'social_gateway_pid=%s\n' "$(pids)"
printf '%s\n' 'QQ／微信新工具已实际启用，模型 schema 和身份路径检查通过'
free -m
