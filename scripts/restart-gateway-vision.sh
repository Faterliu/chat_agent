#!/usr/bin/env bash
# Restart the single manual Hermes gateway via the low-memory launcher and
# report connect/error lines only. Run on the server as hermes.
set -euo pipefail

LOG=/var/lib/hermes/.hermes/logs/agent.log
CFG=/var/lib/hermes/.hermes/config.yaml
EXPECT_SHA="${1:-e3096e70e6387de6335f7996d2a60772fafe9578e6e466e55f0682c167f627c5}"

got_sha="$(sha256sum "$CFG" | cut -d' ' -f1)"
if [ "$got_sha" != "$EXPECT_SHA" ]; then
  echo "REFUSE: config sha256 $got_sha != $EXPECT_SHA"
  exit 2
fi

mapfile -t pids < <(pgrep -f 'hermes gateway run' || true)
if [ "${#pids[@]}" -ne 1 ]; then
  echo "REFUSE: expected exactly 1 gateway, found ${#pids[@]}: ${pids[*]:-none}"
  exit 3
fi
old_pid="${pids[0]}"
echo "stopping pid=$old_pid"
kill -TERM "$old_pid"
for _ in $(seq 1 40); do
  if ! kill -0 "$old_pid" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$old_pid" 2>/dev/null; then
  echo "REFUSE: pid $old_pid still alive after 40s"
  exit 4
fi

start_line=$(( $(wc -l < "$LOG") + 1 ))
echo "log starts at line $start_line"

cd /var/lib/hermes
setsid nohup /var/lib/hermes/start-chat-agent.sh >> "$LOG" 2>&1 < /dev/null &
disown || true

for _ in $(seq 1 60); do
  if pgrep -f 'hermes gateway run' > /dev/null; then break; fi
  sleep 1
done
sleep 20

mapfile -t new_pids < <(pgrep -f 'hermes gateway run' || true)
echo "gateway pids: ${new_pids[*]:-none} (count=${#new_pids[@]})"
if [ "${#new_pids[@]}" -ne 1 ]; then
  echo "FAIL: gateway count ${#new_pids[@]}"
  tail -n 30 "$LOG"
  exit 5
fi
pid="${new_pids[0]}"
ps -o pid,rss,etime,cmd -p "$pid"

echo "--- new log (connect / error / vision) ---"
tail -n +"$start_line" "$LOG" \
  | grep -i -E 'connected|disconnected|reconnect|error|traceback|vision|weixin|qqbot' \
  | tail -n 40 || true
