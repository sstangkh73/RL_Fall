# Report: เพิ่มคำสั่งดูเครดิต Claude และ Codex
Date: 2026-10-09   Status: Done

## Summary
เพิ่ม `auto-loop/tools/credits.ps1` ที่แสดง % โควตาที่ใช้ไปของ Claude และ Codex (window 5 ชม. และ 7 วัน) พร้อมเวลารีเซ็ต
และค่าใช้จ่ายของ Claude เทียบราคา API โดยอ่านจาก log อย่างเดียว ไม่เสียโควตา

## What was done
- `auto-loop/tools/credits.ps1` (ใหม่)
  - Claude: อ่าน `rate_limit_event` ล่าสุดจาก `auto-loop/.loop/iter-*.jsonl` และรวม `total_cost_usd` (วันนี้/ทั้งหมด)
  - Codex: อ่าน `rate_limits` ล่าสุดจาก `~/.codex/sessions/**/rollout-*.jsonl` (หรือ `$CODEX_HOME`) ได้แผน, primary/secondary และเครดิตเสริม
  - ถ้าเวลารีเซ็ตผ่านไปแล้วจะแสดงเป็น 0% และ "รีเซ็ตแล้ว" ใช้สีเขียว/เหลือง/แดงที่ <70/70–90/≥90%
- `auto-loop/README.md`: เพิ่มวิธีใช้ในส่วน "รัน"

## Verification
`pwsh -NoProfile -File auto-loop/tools/credits.ps1` → exit 0
Claude 5 ชม. 7.0% / 7 วัน 61.0% ตรงกับ event ดิบ `"five_hour":{"utilization":0.07}`, `"seven_day":{"utilization":0.61}`
Codex 7 วัน 22% (plus, balance 0) ตรงกับ rollout ล่าสุด ส่วน 5 ชม. รีเซ็ตไปแล้วตอน 07:45 จึงแสดง 0%

## Problems / not done
- ตัวเลขเป็นค่า ณ การเรียกครั้งล่าสุด ไม่ใช่ค่าสด (ข้อมูล Claude มาจากรอบ loop ไม่รวมการใช้ใน session แบบ interactive)
- ไม่ได้แก้ `run-loop.ps1` ให้แสดงเครดิตทุกรอบ เพราะ loop กำลังรัน (PID 3652) และไฟล์นี้ถูก hash ไว้ ถ้าแก้ loop จะหยุด
- ยอด "รวม" ของ Claude นับเฉพาะไฟล์ iter-*.jsonl ที่ยังอยู่ (เมื่อเริ่ม loop ใหม่ เลขรอบเริ่มที่ 1 และเขียนทับไฟล์เดิม)
- ตอนเริ่ม loop ครั้งถัดไป `credits.ps1` จะอยู่ในรายการไฟล์ที่ห้าม AI แก้ เหมือนไฟล์อื่นใน tools/

## Next steps
ถ้าต้องการให้ loop แสดงเครดิตตอนจบทุกรอบ ให้หยุด loop ก่อน แล้วเพิ่ม `& (Join-Path $LoopDir 'tools/credits.ps1')` ใน `run-loop.ps1` หลังบรรทัดที่แสดงผลรอบ

## Update 2 — หน้าจอดูสด + หลอด
- `credits.ps1` เพิ่ม `-Watch` (อัปเดตทุก `-Interval` วิ ค่าเริ่มต้น 60, Ctrl+C ออก) และ `-Width` (ค่าเริ่มต้น 40)
  หลอดใช้ █ (เขียว/เหลือง/แดง ตาม %) ░ = ที่เหลือ และ ┃ = เวลาที่ผ่านไปของ window ใต้หลอดแสดงเวลารีเซ็ต เวลาที่เหลือ และ % เวลาที่ผ่านไป
- เปิดหน้าต่างแยก: `Start-Process pwsh '-NoProfile -File C:\RL_Fall\auto-loop\tools\credits.ps1 -Watch'`
- README อัปเดตแล้ว
- Verification: โหมดปกติ exit 0 → Claude 5 ชม. 7% (เวลาผ่านไป 38%, เหลือ 3 ชม. 5 นาทีจาก 5 ชม. ถูกต้อง), สัปดาห์ 61% (49%),
  Codex สัปดาห์ 22% (22%) โหมด `-Watch` ยังวนอยู่หลัง 5 วิ (ตัดด้วย timeout)
  ใน shell ที่ไม่มีคอนโซลจริง Clear-Host จะ error (handle invalid) ซึ่งไม่เกิดในหน้าต่างเทอร์มินอลปกติ แต่ยังไม่ได้ลองในหน้าต่างจริง
- Bug ที่เจอและแก้แล้ว: `[math]::Max(0, x)` ถูก PowerShell เลือก overload แบบ int ทำให้ % เวลาที่ผ่านไปเป็น 0 ทุกตัว → เปลี่ยนเป็น `0.0`
