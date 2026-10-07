# Report: verify.ps1 ตาม GOAL ใหม่ + run-loop ใช้ WSL ได้ ไม่จำกัดเวลา มีรายงานและจับเวลา
Date: 2026-10-08   Status: Done

## Summary
เขียน `verify.ps1` ใหม่ให้ตัดสินจาก M1–M4 ด้วยไฟล์ผลจริง และปรับ `run-loop.ps1` ให้ไม่จำกัดเวลาโดยค่าเริ่มต้น
Claude สั่งเทรนใน WSL แบบ background ได้ ทุกรอบและทุก job ถูกจับเวลาลงรายงาน
ส่วนที่ทำไม่ได้คือการเปิดสิทธิ์เต็มเครื่องให้ Codex เพราะระบบตรวจสิทธิ์ปฏิเสธ

## What was done
- ย้ายงานตัวอย่าง: `auto-loop/src`, `auto-loop/tests` → `auto-loop/examples/bahttext/`
- ใหม่: `auto-loop/tools/check_goal.py` ตรวจ M1–M4 แล้วเขียน `reports/goal-status.md`
- เขียนใหม่: `auto-loop/verify.ps1` รัน pytest ใน WSL และ `check_goal.py`
- ใหม่: `auto-loop/tools/wsl-job.ps1`, `job-wrapper.sh`, `jobs.ps1`
  rsync โค้ดไป `~/RL_Fall`, รัน job แบบ detached, บันทึก start/end/duration/exit, heartbeat และ `reports/jobs.md`
- เขียนใหม่: `auto-loop/run-loop.ps1`
  - ทำงานที่ root ของโปรเจกต์บน branch `loop/research`
  - MaxIterations/MaxHours = 0 (ไม่จำกัด)
  - allowedTools เพิ่ม WSL, เว็บ, job tools และ python
  - รอ job ด้วยไฟล์ `WAIT_FOR_JOBS`
  - เขียน `reports/loop-report.md` และ `iterations.csv` ทุกรอบ พร้อมเวลารวมตอนจบ
- เขียนใหม่: `auto-loop/PROMPT.md`, `auto-loop/README.md`, `auto-loop/progress.md` (ใส่สถานะเริ่มต้น)
- `auto-loop/GOAL.md`: เพิ่มหัวข้อ "สัญญาไฟล์ผล"
- `.gitignore` ทั้งที่ root (`/.loop/`) และใน `auto-loop/`

## Verification
- `pwsh -File auto-loop/verify.ps1`: pytest ผ่านใน WSL ส่วน M1–M4 FAIL เพราะยังไม่มีไฟล์ milestone ซึ่งถูกต้อง
- ทดสอบ `check_goal.py` ด้วย m1_runs.json ชั่วคราวที่ชี้ผล 3 seeds ของวันที่ 7 ต.ค.:
  ได้ตัวเลขตรงกับตารางในแผน (drift 7.9/29.8/8.4 ซม., รอดที่ 0.10 เฉลี่ย 67%) และ FAIL เพราะ run เก่าและ drift เกิน แล้วลบไฟล์ทดสอบออก
- ทดสอบ wsl-job.ps1 ด้วย job สั้น 2 ครั้ง (exit 0 และ exit 3): บันทึกสถานะ เวลา และ jobs.md ถูก แล้วลบออก
  พบและแก้บั๊กปฏิทินพุทธศักราช (2569) ใน id และวันที่สลับเดือน โดยใช้ InvariantCulture + epoch
- parse ไฟล์ .ps1 ทั้งหมดด้วย PowerShell parser ไม่มี error, `bash -n` job-wrapper.sh ผ่าน
- **ยังไม่ได้รัน `run-loop.ps1` จริง** (เสียเงินและใช้เวลา) จึงยังไม่ได้ทดสอบ claude -p กับ allowedTools ใหม่และการ commit ลง branch

## Problems / not done
- **Codex สิทธิ์เต็ม:** การแก้ `tools/codex.sh` เป็น `--sandbox danger-full-access` ถูกระบบตรวจสิทธิ์ปฏิเสธ จึงไม่ได้แก้
  `codex.sh` ยังเหมือนเดิม Codex จึงยังรันคำสั่งบน Windows ไม่ได้ ผู้ใช้ต้องตัดสินใจเอง
- Claude ในลูปไม่ได้สิทธิ์ Bash ทุกคำสั่งบน Windows ได้แค่รายการใน `$AllowedTools` แต่ใน WSL รันได้ทุกคำสั่ง
- seed 63003 (8.4 ซม.) ก็ไม่ผ่านเกณฑ์ ≤ 8 ซม. ตามตัวตรวจ ทั้งที่ในแผนนับว่าผ่าน แปลว่าตอนนี้ M1 ผ่านแค่ 1/3
- เกณฑ์ที่ตั้งขึ้นใหม่และควรยืนยัน: รอดเฉลี่ยที่ 0.10 ≥ 60%, M2 tolerance 5 จุด, ≥ 48 episodes, M4 ≤ 16,000 ตัวอักษร

## Next steps
- ตัดสินใจเรื่องสิทธิ์ของ Codex แล้วรัน `pwsh -File auto-loop/run-loop.ps1 -MaxIterations 1` ก่อน 1 รอบ เพื่อทดสอบจริง

## Changes after review (8 ต.ค.)
- ผู้ใช้อนุญาตให้ Codex รันแบบไม่มี sandbox และยืนยันเกณฑ์ที่เหลือตามที่เสนอ
- `auto-loop/tools/codex.sh`: เปลี่ยนเป็น `--sandbox danger-full-access -C <root>`, ย้าย log ไป `auto-loop/.loop/codex/` และแสดงเวลาที่ใช้
- ทดสอบ: Codex รัน `git log --oneline -1` ได้ (exit 0, 18 วินาที) จากเดิมที่ถูกบล็อก
- เอาบรรทัด `/.loop/` ที่เพิ่มใน `.gitignore` ของ root ออก เพราะไม่ต้องใช้แล้ว
