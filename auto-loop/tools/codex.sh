#!/usr/bin/env bash
# ส่งงานให้ Codex ทำแบบไม่ถามกลับ แล้วพิมพ์ข้อความสรุปสุดท้ายของ Codex พร้อมเวลาที่ใช้
# ใช้: bash auto-loop/tools/codex.sh "คำสั่งงานแบบละเอียด"   (รันจาก root ของโปรเจกต์)
# Codex รันแบบไม่มี sandbox (danger-full-access) ตามที่ผู้ใช้อนุญาต 8 ต.ค. 2026
# เพราะ sandbox บน Windows เครื่องนี้บล็อกการรันคำสั่งทุกตัว (CreateProcessAsUserW failed: 5)
set -u

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "usage: bash auto-loop/tools/codex.sh \"task\"" >&2
  exit 2
fi

root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
dir="$root/auto-loop/.loop/codex"
mkdir -p "$dir"
ts=$(date +%Y%m%d-%H%M%S)
log="$dir/$ts.log"
last="$dir/$ts.last.md"
start=$(date +%s)

codex exec --sandbox danger-full-access -C "$root" --skip-git-repo-check --output-last-message "$last" "$1" >"$log" 2>&1
code=$?

echo "[codex exit=$code | $(( $(date +%s) - start ))s | full log: $log]"
if [ -s "$last" ]; then
  cat "$last"
else
  tail -n 80 "$log"
fi
exit $code
