# Report: ให้ loop บริหารโควตา Claude/Codex เอง
Date: 2026-10-09   Status: Done (ยังไม่ได้รัน loop จริงทั้งรอบ)

## Summary
ก่อนเริ่มทุกรอบ loop จะอ่านโควตาสดของ Claude และ Codex แล้วเลือกตัวที่โควตาเหลือคุ้มกว่าเป็นตัวนำ ส่วนอีกตัวเป็นตัวช่วยรีวิว
ทั้งสองตัวสลับบทกันได้ ถ้าตัวช่วยใกล้เต็มจะปฏิเสธงานด้วย `QUOTA:` และถ้าใช้ไม่ได้ทั้งคู่ loop จะรอจนตัวแรกกลับมา

## What was done
- `auto-loop/tools/quota.ps1` (ใหม่): อ่านโควตาสด (Codex ผ่าน `codex app-server` → `account/rateLimits/read` ไม่เสีย token,
  Claude ผ่าน haiku 1 turn ~$0.0006) cache ไว้ที่ `.loop/quota-cache.json` (Claude 10 นาที / Codex 1 นาที) ถ้าถามสดไม่ได้จะใช้ค่าจาก log
  คะแนน = (100 − ใช้ไปใน 5 ชม.) / ชม.ที่เหลือถึงรีเซ็ต × ตัวคูณสัปดาห์ (r² ถ้าใช้เร็วกว่าเวลา, r ถ้าช้ากว่า สูงสุด 2)
  ใช้ไม่ได้: 5 ชม. ≥ 90% / สัปดาห์ ≥ 95% (env `QUOTA_LIMIT_5H`, `QUOTA_LIMIT_WEEK`) มีโหมด `-Json`, `-Check <agent>` และ dot-source
- `auto-loop/tools/claude.ps1` (ใหม่): Codex เรียก Claude เป็นตัวช่วย (`-TaskFile`/`-Task`) บันทึกลง `reports/claude-helper.md`
  ตัวช่วยเรียก Codex และสั่ง job ไม่ได้
- `auto-loop/tools/codex.sh`: เช็คโควตาก่อนเรียก ถ้าใกล้เต็มจะตอบ `QUOTA:` และ exit 3
- `auto-loop/run-loop.ps1`: dot-source quota.ps1, เลือกตัวนำก่อนทุกรอบ, ถ้าใช้ไม่ได้ทั้งคู่จะรอ (STOP หยุดได้),
  ต่อท้าย prompt ด้วยส่วน "โควตาและบทบาทรอบนี้", รัน `claude -p` หรือ `codex exec ... -` (stdin),
  เพิ่มคอลัมน์ "ตัวนำ" ใน loop-report.md และ `lead,quota_wait_s` ใน iterations.csv (ไฟล์เก่าเติมหัวคอลัมน์ให้), อนุญาตให้ Claude เรียก quota.ps1
- `auto-loop/PROMPT.md`: ใช้ได้ทั้งสองตัว, ข้อ 4 แบ่งงานตามโควตา, วิธีเรียกตัวช่วยทั้งสองทาง, หมายเหตุ shell ของ Codex บน Windows,
  ห้ามใช้เครดิตรีเซ็ตของ Codex
- `auto-loop/tools/credits.ps1`: ใช้ค่าสดจาก quota.ps1, แสดงตัวนำรอบหน้า และจำนวนเครดิตรีเซ็ตฟรีของ Codex (`-NoProbe` = ไม่ถามสด)
- `auto-loop/README.md`: เพิ่มส่วน "บริหารโควตา Claude / Codex"
- หยุด loop เดิมด้วย STOP (จบ 11:15:30) แก้ไฟล์เสร็จแล้วลบ STOP ออก

## Verification
- `quota.ps1`: ค่าสด Claude 5 ชม. 22% / สัปดาห์ 62%, Codex 3% / 23% → ตัวนำ claude (34 > 20.8) เพราะ 5 ชม. ของ Claude รีเซ็ตใน 80 นาที
- สถานการณ์ทดสอบ: ตัวอย่างผู้ใช้ (80%/80%, 20 นาทีเทียบกับ 4 ชม.) → 240 เทียบกับ 20 ✓; สัปดาห์ 90% ตอนเวลาผ่านไปครึ่งเดียว → 12 เทียบกับ 28 (ไปใช้อีกตัว) ✓;
  5 ชม. 92% / สัปดาห์ 96% → ใช้ไม่ได้ ✓; window รีเซ็ตไปแล้ว → นับเป็น 0% ✓
- `QUOTA_LIMIT_5H=2`: `codex.sh` และ `claude.ps1` ตอบ `QUOTA:` exit 3 ✓ และเมื่อใช้ไม่ได้ทั้งคู่ → "รอถึง 23:00" ✓
- `claude.ps1` งานจริง: exit 0, 12 วิ, $0.14, ตอบถูก (90%) ✓
- `codex exec ... -` ผ่าน pipe ใน pwsh: ตอบ "pong" exit 0 ✓
- parse ไฟล์ PowerShell ทั้ง 4 ไฟล์ผ่าน, `bash -n codex.sh` ผ่าน
- **ยังไม่ได้รัน run-loop.ps1 จริงทั้งรอบ** (โดยเฉพาะทางที่ Codex เป็นตัวนำ) ทดสอบแค่ทีละส่วน

## Problems / not done
- bug ที่เจอระหว่างทำแล้วแก้แล้ว: locale ไทยทำให้ได้ปี 2569 → บังคับ InvariantCulture; event `result` ของ claude ไม่ได้ขึ้นต้นด้วย `"type"` → parse JSON แทน;
  dot-source ทับพารามิเตอร์ `$NoProbe` ของ credits.ps1 → เก็บค่าไว้ก่อน
- ตอน Codex เป็นตัวนำ หน้าจอจะเห็นแค่ข้อความดิบของ `codex exec` (ไม่มี turns/ค่าใช้จ่าย) ในรายงานจึงใส่ "-"
- `WAIT_FOR_JOBS` ถูกลบไปตอน STOP แต่ job `20261009-105614-s2anc_wide` ยังรันอยู่ รอบแรกหลังเปิด loop ใหม่ ตัวนำจะเห็น job แล้วน่าจะตั้ง WAIT_FOR_JOBS เอง
- เลขรอบของ loop เริ่มที่ 1 ทุกครั้งที่เปิดใหม่ จึงเขียนทับ `.loop/iter-NNN.*` เดิม (เป็นมาก่อนแล้ว ไม่ได้แก้)

## Next steps
- เปิด loop: `pwsh -File C:\RL_Fall\auto-loop\run-loop.ps1` แล้วดูรอบแรกว่าบรรทัด `[โควตา] ตัวนำ ...` และคอลัมน์ "ตัวนำ" ออกถูก
- ถ้าอยากให้ใช้ Codex มากขึ้นหรือน้อยลง ปรับเกณฑ์ด้วย env หรือแก้สูตรใน `Measure-Quota` ของ quota.ps1

## Update 2 — อ่านโควตา Claude จาก /usage (ตรงกับหน้าแอป)
- ปัญหา: ผู้ใช้แจ้งว่าตัวเลข Claude ไม่ตรงกับหน้าแอป สาเหตุคือ probe ด้วย haiku ถูก cache ไว้ 10 นาที (ตอนนั้นอ่านได้ 7% แต่แอปบอก 16%)
- แก้: `quota.ps1` อ่านจาก `claude -p "/usage" --output-format json --no-session-persistence` ซึ่งเป็นคำสั่ง local ($0, 0 token)
  ใช้ตัวเลขชุดเดียวกับหน้า usage ของแอป และไม่เขียน transcript หรือ history (เช็คแล้ว: history.jsonl 24 → 24 บรรทัด)
  /usage บอกเวลารีเซ็ตแค่ระดับชั่วโมง จึงใช้เวลาที่แม่นจาก rate_limit_event ล่าสุดถ้าห่างกันไม่เกิน 1 ชม.
  ถ้ามีเพดานรายสัปดาห์แยกรุ่น จะใช้ % ที่สูงสุด ส่วน haiku probe เหลือไว้เป็นทางสำรอง และลด cache ของ Claude เหลือ 1 นาที
- Verification: ได้ 16% / 66% ตรงกับ /usage; parse เวลา "Oct 10, 12am", "Oct 12, 11:30pm", "3pm", "Jan 2, 1am" ถูก; ไฟล์ PowerShell parse ผ่านทั้งหมด
  พอใช้ค่าที่ถูกต้อง Claude สัปดาห์ 66% ขณะที่เวลาผ่านไป 56% → คะแนนลดลง ตัวนำรอบใหม่เป็น codex (26.7 > 16)
- ทาง Codex เป็นตัวนำได้ใช้จริงแล้ว: รอบ 2–3 ของ loop ที่เริ่ม 12:37 (16 และ 29 นาที, verify ทำงานต่อได้)
- Restart loop (STOP ตอน 20:52 ขณะรอ job `20261009-202136-s2dmg20k`) เพื่อโหลดโค้ดใหม่ เพราะ quota.ps1/credits.ps1 เป็นไฟล์ที่ loop เดิมห้ามแก้

## Update 3 — loop ตายระหว่างรอ job (00:22, 10 ต.ค.)
- อาการ: `You cannot call a method on a null-valued expression` ที่ `run-loop.ps1:181` (Get-ActiveJobs) หลังรอ job มา 3:20 ชม.
- ต้นเหตุ: `job-wrapper.sh` เขียน heartbeat ทุก 60 วิด้วย `date +%s > file` ซึ่งล้างไฟล์ก่อนเขียน ถ้า loop อ่านตรงจังหวะนั้นจะได้ `$null` แล้ว `.Trim()` error
  ทำให้เกิดซ้ำได้ด้วยไฟล์ heartbeat ว่าง ส่วน `tools/jobs.ps1:19` มี bug เดียวกัน และไฟล์สถานะ .json ก็อาจอ่านเจอแบบว่างหรือไม่ครบตอน job จบ
- แก้: `Get-HeartbeatEpoch` (ถ้าอ่านไม่ได้ให้ใช้เวลาแก้ไขไฟล์), ถ้า .json อ่านไม่ได้ถือว่ายังรันอยู่ (รอบ poll หน้าจะอ่านได้), แก้ jobs.ps1 แบบเดียวกัน
  เพิ่ม `catch` ใน run-loop ให้ข้อความจบบอก error จริง (เดิมขึ้นว่า "ครบจำนวนรอบแต่ verify ยังไม่ผ่าน" ซึ่งทำให้เข้าใจผิด)
- Verification: ทดสอบ 5 กรณี (heartbeat ว่าง, json ไม่ครบ, stale, ยังมีชีวิต, จบแล้ว) ได้ตามคาด, parse ผ่าน, jobs.ps1 รันได้
- ผลกระทบ: job `s2dmg20k` จบปกติตอน 00:43 (exit 0) แต่ loop ไม่ได้ทำงานระหว่าง 00:22 จนถึงตอนเปิดใหม่
