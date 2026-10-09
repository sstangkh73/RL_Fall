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

# โควตา Codex ใกล้เต็ม → ไม่เรียก บอกให้ผู้เรียกทำเอง (ข้อความขึ้นต้นด้วย QUOTA:)
quota_msg=$(pwsh -NoProfile -File "$root/auto-loop/tools/quota.ps1" -Check codex)
if [ $? -eq 3 ]; then echo "$quota_msg"; exit 3; fi
dir="$root/auto-loop/.loop/codex"
mkdir -p "$dir"
ts=$(date +%Y%m%d-%H%M%S)
log="$dir/$ts.log"
last="$dir/$ts.last.md"
start=$(date +%s)

codex exec --sandbox danger-full-access -C "$root" --skip-git-repo-check --output-last-message "$last" "$1" >"$log" 2>&1
code=$?

dur=$(( $(date +%s) - start ))
if [ -s "$last" ]; then reply=$(cat "$last"); else reply=$(tail -n 80 "$log"); fi
# คำสั่ง shell ที่ Codex รันเอง (บรรทัดถัดจาก "exec" ใน log)
ran=$(awk 'prev == "exec" { print } { prev = $0 }' "$log" | head -n 40)

# บันทึกถาวรให้คนอ่าน: สั่งอะไร, Codex รันอะไร, ตอบอะไร
report="$root/auto-loop/reports/codex.md"
mkdir -p "$(dirname "$report")"
[ -f "$report" ] || printf '# Codex calls\n\nทุกครั้งที่ Claude ในลูปสั่งงาน Codex ผ่าน tools/codex.sh\n' > "$report"
{
  printf '\n## %s  (exit %s, %ss)\n\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$code" "$dur"
  printf '**Claude สั่ง:**\n\n````text\n%s\n````\n\n' "$1"
  if [ -n "$ran" ]; then printf '**Codex รัน:**\n\n````text\n%s\n````\n\n' "$ran"; fi
  printf '**Codex ตอบ:**\n\n%s\n\n' "$reply"
  printf 'log เต็ม: `auto-loop/.loop/codex/%s.log`\n' "$ts"
} >> "$report"

echo "[codex exit=$code | ${dur}s | full log: $log]"
printf '%s\n' "$reply"
exit $code
