#!/usr/bin/env bash
# 内存参数必须在 Python 启动前设置；不修改聊天、工具或调度配置。
set -euo pipefail
export HERMES_HOME=/var/lib/hermes/.hermes
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export MALLOC_ARENA_MAX=2
export MALLOC_TRIM_THRESHOLD_=131072
cd /var/lib/hermes
exec /var/lib/hermes/.local/bin/hermes gateway run
