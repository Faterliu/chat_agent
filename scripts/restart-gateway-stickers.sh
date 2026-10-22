#!/usr/bin/env bash
# 停旧网关 → 低内存启动器启一个 → 打印 PID/连接/日志尾部。只动这一个进程。
set -euo pipefail

old=$(pgrep -f 'hermes gateway run' | head -1 || true)
echo "old pid: ${old:-none}"
if [ -n "${old}" ]; then
  kill -TERM "$old"
  for _ in $(seq 1 30); do
    pgrep -f 'hermes gateway run' >/dev/null || break
    sleep 1
  done
fi
echo "after stop: $(pgrep -f 'hermes gateway run' || echo none)"

setsid nohup /var/lib/hermes/start-chat-agent.sh >> /var/lib/hermes/.hermes/logs/agent.log 2>&1 < /dev/null &
sleep 15

echo "new pid: $(pgrep -f 'hermes gateway run' | head -1)"
echo "instances: $(pgrep -c -f 'hermes gateway run')"
ps -o pid,etime,rss,cmd -p "$(pgrep -f 'hermes gateway run' | head -1)"
tail -n 25 /var/lib/hermes/.hermes/logs/agent.log
