#!/usr/bin/env bash
# รัน job หนึ่งตัวใน WSL แล้วจับเวลา (เรียกจาก wsl-job.ps1 เท่านั้น)
# ใช้: job-wrapper.sh <job-id> <jobs-dir (WSL path)>
# เขียน <id>.json (สถานะ), <id>.heartbeat (ทุก 60 วิ), <id>.log และต่อท้าย ../jobs.md เมื่อจบ
set -u
ID="$1"
DIR="$2"
CMD="$DIR/$ID.cmd"
LOG="$DIR/$ID.log"
STATUS="$DIR/$ID.json"
HB="$DIR/$ID.heartbeat"
TABLE="$DIR/../jobs.md"

hms() { printf '%d:%02d:%02d' $(($1 / 3600)) $(($1 % 3600 / 60)) $(($1 % 60)); }
status() {  # state end duration exit
  printf '{"id": "%s", "state": "%s", "start": "%s", "start_epoch": %d, "end": %s, "duration_s": %s, "exit_code": %s, "pid": %d}\n' \
    "$ID" "$1" "$START_ISO" "$START" "$2" "$3" "$4" $$ > "$STATUS"
}

START=$(date +%s)
START_ISO=$(date -d "@$START" '+%Y-%m-%dT%H:%M:%S%z')
status running null null null
( while :; do date +%s > "$HB"; sleep 60; done ) &
BEAT=$!

{
  echo "=== job $ID  start $START_ISO"
  echo "=== command:"; cat "$CMD"; echo "==="
} > "$LOG"
cd ~/RL_Fall && bash "$CMD" >> "$LOG" 2>&1
CODE=$?

END=$(date +%s)
END_ISO=$(date -d "@$END" '+%Y-%m-%dT%H:%M:%S%z')
DUR=$((END - START))
kill "$BEAT" 2>/dev/null
date +%s > "$HB"
echo "=== end $END_ISO  duration $(hms $DUR)  exit $CODE" >> "$LOG"
if [ "$CODE" -eq 0 ]; then STATE=done; else STATE=failed; fi
status "$STATE" "\"$END_ISO\"" "$DUR" "$CODE"

if [ ! -f "$TABLE" ]; then
  printf '# Jobs\n\nทุก job ที่รันผ่าน tools/wsl-job.ps1 (เวลาเป็นเวลาเครื่อง)\n\n| job | เริ่ม | จบ | ใช้เวลา | ชั่วโมง | exit |\n|---|---|---|---|---:|---:|\n' > "$TABLE"
fi
printf '| %s | %s | %s | %s | %s | %s |\n' "$ID" "$START_ISO" "$END_ISO" "$(hms $DUR)" \
  "$(awk -v s="$DUR" 'BEGIN { printf "%.2f", s / 3600 }')" "$CODE" >> "$TABLE"
exit "$CODE"
