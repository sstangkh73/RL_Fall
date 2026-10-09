# Claude + Codex Auto Loop (RL Fall)

ลูปที่ให้ Claude ทำงานวิจัยต่อไปเรื่อยๆ จนกว่า `verify.ps1` จะผ่าน โดยไม่ต้องหยุดถามคน
Claude ส่งงานบางส่วนให้ Codex ได้ และสั่งเทรนใน WSL ได้ ทุกรอบและทุก job ถูกจับเวลาและบันทึกเป็นรายงาน

```
run-loop.ps1 ──► claude -p (อ่าน PROMPT.md, ทำงานที่ C:\RL_Fall)
     ▲               ├─ วางแผน / แก้โค้ด / วิเคราะห์ผล
     │               ├─ tools/wsl-job.ps1 ──► เทรนใน WSL (background, จับเวลา)
     │               └─ tools/codex.sh     ──► Codex
     │
     ├─ เช็กว่าไฟล์ที่ห้ามแก้ยังไม่ถูกแก้
     ├─ git commit ลง branch loop/research
     ├─ ถ้ามี WAIT_FOR_JOBS → รอจน job จบ (ไม่เรียก Claude ระหว่างรอ)
     └─ verify.ps1 (pytest + M1–M4) ── ผ่าน → จบ / ไม่ผ่าน → รอบถัดไป
```

## ไฟล์

| ไฟล์ | หน้าที่ | ใครแก้ |
|---|---|---|
| `GOAL.md` | เป้าหมาย, milestone M1–M4, สัญญาไฟล์ผล | คน |
| `verify.ps1`, `tools/check_goal.py` | ตัวตัดสิน: exit 0 = เสร็จ | คน |
| `PROMPT.md` | คำสั่งที่ Claude ได้รับทุกรอบ | คน |
| `tools/wsl-job.ps1`, `job-wrapper.sh`, `jobs.ps1` | รัน job ใน WSL แบบ background และจับเวลา | คน |
| `progress.md` | ความจำระหว่างรอบ | AI |
| `milestones/` | ไฟล์ที่ชี้ไปยังผลจริงของแต่ละ milestone | AI |
| `reports/loop-report.md`, `iterations.csv` | เวลาและผลของทุกรอบ | ลูป |
| `reports/jobs.md`, `reports/jobs/` | เวลา, log และสถานะของทุก job | ลูป |
| `reports/goal-status.md` | สถานะ M1–M4 ล่าสุด | verify |
| `reports/codex.md` | ทุกครั้งที่สั่ง Codex: Claude สั่งอะไร, Codex รันคำสั่งอะไร, ตอบอะไร, ใช้เวลาเท่าไร | codex.sh |
| `.loop/iter-NNN.log` | ทุกอย่างที่ Claude ทำในรอบนั้น: ข้อความ, tool ที่เรียก, ผลย่อ, ค่าใช้จ่าย | ลูป |
| `.loop/iter-NNN.jsonl` | event ดิบจาก `claude --output-format stream-json` | ลูป |
| `examples/bahttext/` | งานตัวอย่างเดิมของเทมเพลต (ไม่ได้ใช้) | – |

## รัน

```
pwsh -File auto-loop/run-loop.ps1
```

- **ไม่จำกัดเวลาและจำนวนรอบ** เป็นค่าเริ่มต้น ถ้าต้องการจำกัด ใส่ `-MaxHours 24` หรือ `-MaxIterations 30`
- **หยุด:** สร้างไฟล์ `auto-loop/STOP` (หยุดก่อนรอบถัดไป และหยุดรอ job ด้วย) หรือกด Ctrl+C
  แต่ job ใน WSL จะรันต่อจนจบ ถ้าต้องการหยุด job ด้วย ให้ใช้ `wsl --shutdown`
- **เห็นสดบนหน้าจอ:** ทุกข้อความของ Claude (`[Claude]`), ทุก tool ที่เรียก (`▶ Bash: ...`) พร้อมผลย่อ (`↳`),
  งานที่สั่ง Codex (`[Claude → Codex]`) และคำตอบเต็มของ Codex (`[Codex → Claude]`) แล้วตอนจบรอบจะแสดงจำนวน turns และค่าใช้จ่าย
- **ดูความคืบหน้า:** `reports/loop-report.md`, `reports/jobs.md`, `reports/goal-status.md`, `progress.md`
  และสถานะ job ใช้ `pwsh -NoProfile -File auto-loop/tools/jobs.ps1`
- **ดูเครดิต Claude/Codex:** `pwsh -NoProfile -File auto-loop/tools/credits.ps1` แสดงหลอดโควตา 5 ชม. และสัปดาห์ พร้อมเวลารีเซ็ต
  เปิดหน้าต่างแยกที่อัปเดตทุก 60 วิ: `Start-Process pwsh '-NoProfile -File C:\RL_Fall\auto-loop\tools\credits.ps1 -Watch'`
  (ค่าสดจาก quota.ps1 พร้อมบอกตัวนำรอบหน้า) █ = ใช้ไป, ┃ = เวลาที่ผ่านไปของ window
- **ย้อนกลับ:** ลูป commit ทุกรอบลง branch `loop/research` ให้ใช้ `git log` หา commit ที่ต้องการ แล้ว `git reset --hard <commit>`

## บริหารโควตา Claude / Codex

ก่อนเริ่มทุกรอบ ลูปเรียก `tools/quota.ps1` เพื่ออ่านโควตาสดของทั้งสองตัว แล้วเลือกตัวนำ (ทำงานที่กิน token มาก) กับตัวช่วย (รีวิว / ความเห็นที่สอง)
- คะแนน = (% ที่เหลือใน 5 ชม. / ชั่วโมงที่เหลือถึงรีเซ็ต) × ตัวคูณรายสัปดาห์ ถ้าโควตาใกล้รีเซ็ตแต่ยังเหลือเยอะ ให้ใช้ก่อน ไม่งั้นเสียเปล่า
  ถ้าใช้รายสัปดาห์เร็วกว่าเวลาจะโดนลดคะแนนแรง (กำลังสอง)
- ตัวที่ 5 ชม. ≥ 90% หรือสัปดาห์ ≥ 95% ใช้ไม่ได้ (ปรับด้วย env `QUOTA_LIMIT_5H`, `QUOTA_LIMIT_WEEK`) ถ้าใช้ไม่ได้ทั้งคู่ ลูปจะรอ
- ตัวนำได้ prompt เดียวกัน (`PROMPT.md`) และมีหัวข้อ "โควตาและบทบาทรอบนี้" ต่อท้าย
  Claude เรียก Codex ด้วย `codex.sh` ส่วน Codex เรียก Claude ด้วย `claude.ps1 -TaskFile` ถ้าตัวช่วยใกล้เต็ม จะตอบ `QUOTA:` และไม่ทำงาน
- ค่าสด: Codex ถามผ่าน `codex app-server` (ไม่เสีย token), Claude ถามด้วย haiku 1 ครั้ง (~$0.0006) cache ไว้ที่ `.loop/quota-cache.json`
- ดูแผนตอนนี้: `pwsh -NoProfile -File auto-loop/tools/quota.ps1` ส่วนตัวนำแต่ละรอบดูได้ในคอลัมน์ "ตัวนำ" ของ `reports/loop-report.md`
- งานที่ Codex สั่ง Claude บันทึกไว้ที่ `reports/claude-helper.md`

## สิทธิ์ของ Claude ในลูป

ใน `$AllowedTools` ของ `run-loop.ps1` Claude ได้สิทธิ์ดังนี้:
- แก้ไฟล์ได้ทุกไฟล์ (แต่ถ้าแก้ไฟล์ที่ห้ามแก้ ลูปจะหยุด)
- ค้นเว็บ
- รันคำสั่ง WSL ได้ทุกคำสั่ง (`wsl.exe ...`) รวมถึงเครื่องมือ job, Codex, `python`, `nvidia-smi` และ git แบบอ่าน

คำสั่งอื่นนอกรายการจะถูกปฏิเสธอัตโนมัติ (โหมด headless จึงไม่ค้างรอคน) ถ้าต้องการให้ใช้เครื่องมือเพิ่ม ให้เพิ่มเข้าไปในรายการนี้

## ข้อควรรู้

- **โค้ดสองที่:** Claude แก้โค้ดที่ `C:\RL_Fall` ส่วนการเทรนรันที่ `~/RL_Fall` ใน WSL
  `wsl-job.ps1` จะ rsync `src/ scripts/ tests/ configs/ assets/` ไปให้ก่อนรันทุกครั้ง โดยไม่ลบไฟล์ปลายทาง
- **Codex** รันแบบไม่มี sandbox (`danger-full-access`) จึงแก้ไฟล์และรันคำสั่งได้ทั้งเครื่อง
  ที่ไม่ใช้ sandbox เพราะ sandbox บน Windows เครื่องนี้บล็อกการรันคำสั่งทุกตัว
  log ของ Codex อยู่ที่ `auto-loop/.loop/codex/`
- **ค่าใช้จ่าย:** คิดทั้งฝั่ง Claude และ OpenAI เมื่อไม่จำกัดเวลา ควรเปิดดู `reports/loop-report.md` เป็นระยะ
