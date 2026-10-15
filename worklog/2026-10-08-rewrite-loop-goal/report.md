# Report: เขียน GOAL.md ของ auto-loop ใหม่ให้เป็นงานวิจัย RL Fall
Date: 2026-10-08   Status: Done

## Summary
เปลี่ยน `auto-loop/GOAL.md` จากงานตัวอย่าง BAHTTEXT เป็นเป้าหมายจริงของงานวิจัย
มีคำถามวิจัยระยะยาว 2 ข้อ (S2 และ S3) และเป้าหมายระยะสั้นคือชุดหลักฐานสำหรับขอ LANTA และคุยกับอาจารย์
แบ่งเป็น milestone M1–M4 พร้อมเกณฑ์ผ่าน

## What was done
- เขียนใหม่ทั้งไฟล์ `auto-loop/GOAL.md`
- เกณฑ์ M1 และ M2 เอามาจาก gate ใน `planning/Curriculum_Plan_TH.md` (หลักการ S1 และข้อ 5)

## Verification
อ่านทวนเทียบกับ `planning/Curriculum_Plan_TH.md` แล้ว ไม่มีการรันโค้ด เพราะงานนี้แก้แค่เอกสาร

## Problems / not done
- `auto-loop/verify.ps1` ยังรัน test ของ BAHTTEXT ส่วน `tests/` กับ `src/` ยังเป็นงานตัวอย่าง ถ้ารันลูปตอนนี้ verify จะไม่ตรงกับเป้าใหม่
- เกณฑ์ "รอดเฉลี่ยที่ 0.10 ≥ 60%" ใน M1 เป็นค่าที่ตั้งขึ้นใหม่ ไม่มีในแผนเดิม (ตอนนี้ได้ 67%) ผู้ใช้ควรยืนยัน
- `run-loop.ps1` จำกัดคำสั่ง Bash ละไม่เกิน 30 นาที และยังไม่มีสิทธิ์เรียก WSL จึงยังเทรนจากในลูปไม่ได้

## Next steps
- เขียน `verify.ps1` ให้ตรวจเกณฑ์ M1 (เช่น อ่าน `survival_curve.json` ทั้ง 3 seeds) และเพิ่มสิทธิ์ `wsl` ใน `$AllowedTools`
- ตัดสินใจว่าจะย้ายลูปไปไว้ที่ root ของโปรเจกต์ตาม README ของลูปหรือไม่
