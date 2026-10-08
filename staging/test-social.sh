#!/usr/bin/env bash
# 临时源码和测试 venv；不接入生产提供方，不启动网关。
set -euo pipefail
umask 077
repo=/var/lib/hermes/.hermes/hermes-agent
work=/var/lib/hermes/social-test-20261008-fix
if [[ ! -e "$work" ]]; then
    mkdir -m 700 "$work"
    git -C "$repo" archive HEAD | tar -x -C "$work"
    git -C "$repo" diff --binary > "$work/current-local.patch"
    git -C "$work" apply "$work/current-local.patch"
    for file in tools/gateway_user_scope.py tools/qq_reminder.py tests/tools/test_gateway_user_scope.py tests/tools/test_qq_reminder.py tools/social_store.py tools/social_tool.py gateway/social_runtime.py tests/tools/test_social.py; do
        cp -p "$repo/$file" "$work/$file"
    done
fi
git -C "$work" apply --check /var/lib/hermes/social-silent-fix.patch
git -C "$work" apply /var/lib/hermes/social-silent-fix.patch
"$repo/venv/bin/python" -m venv "$work/.venv"
site="$work/.venv/lib/python3.12/site-packages"
printf '%s\n' "$repo/venv/lib/python3.12/site-packages" > "$site/production-dependencies.pth"
/var/lib/hermes/.hermes/bin/uv pip install --python "$work/.venv/bin/python" --index-url https://pypi.tuna.tsinghua.edu.cn/simple pytest pytest-asyncio pytest-timeout
cd "$work"
scripts/run_tests.sh -j 1 tests/tools/test_social.py tests/tools/test_gateway_user_scope.py tests/tools/test_qq_reminder.py tests/tools/test_cronjob_tools.py -q
