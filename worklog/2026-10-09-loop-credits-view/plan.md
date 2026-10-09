# Plan: เพิ่มคำสั่งดูเครดิต Claude และ Codex
Date: 2026-10-09

## Goal
มีคำสั่งเดียวที่แสดงโควตาที่ใช้ไปของ Claude และ Codex (5 ชม. / 7 วัน, เวลารีเซ็ต) และค่าใช้จ่ายรวมของ loop

## Context
- Claude: `auto-loop/.loop/iter-*.jsonl` (stream-json) มี event `rate_limit_event` → `unifiedWindows.five_hour/seven_day.utilization` + `resetsAt`
  และ event `result` มี `total_cost_usd` ต่อรอบ
- Codex: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` มี `rate_limits` → `primary` (300 นาที), `secondary` (10080 นาที), `credits`, `plan_type` (plus)
- loop กำลังรันอยู่ (PID 3652, รอบ 5) `run-loop.ps1` และไฟล์ใน `tools/` ที่มีอยู่ตอนเริ่ม loop ถูก hash ไว้ ถ้าแก้ loop จะหยุด
  ไฟล์ใหม่ใน `tools/` ไม่อยู่ในรายการ hash ของรอบนี้

## Steps
1. เขียน `auto-loop/tools/credits.ps1` (อ่านอย่างเดียว ไม่เรียก API ไม่เสีย token)
2. ทดสอบรันด้วย pwsh และเทียบตัวเลขกับ jsonl ดิบ
3. เพิ่มวิธีใช้ใน `auto-loop/README.md`

## How it will be verified
`pwsh -NoProfile -File auto-loop/tools/credits.ps1` แสดงตัวเลขตรงกับ event ล่าสุดในไฟล์ jsonl

## Risks / assumptions
- ตัวเลขเป็น snapshot จากการเรียกครั้งล่าสุด ไม่ใช่ค่าสด (ค่าสดต้องเรียก API ซึ่งกินโควตา) จะแสดงเวลาของข้อมูลกำกับไว้
- ค่า $ ของ Claude เป็นราคาเทียบ API ไม่ใช่เงินที่ถูกเก็บจริง (ใช้ subscription)
- ยังไม่แก้ `run-loop.ps1` ให้โชว์เครดิตทุกรอบ เพราะจะทำให้ loop ที่รันอยู่หยุด

## Changes during work
ผู้ใช้ขอเพิ่ม: ให้เป็นคำสั่งที่เปิดดูในเทอร์มินอลแยก และแสดงหลอดเป็นภาพทั้งโควตา 5 ชม. และสัปดาห์
→ เพิ่ม `-Watch [-Interval 60]` (ล้างจอแล้ววาดใหม่) และหลอด █/░ ยาว 40 ช่อง พร้อมเครื่องหมาย ┃ แสดงเวลาที่ผ่านไปของ window
