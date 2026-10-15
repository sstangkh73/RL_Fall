# Plan: verify.ps1 ตาม GOAL ใหม่ + run-loop ใช้ทรัพยากรเครื่องได้เต็ม (รวม WSL) ไม่จำกัดเวลา มีรายงานและจับเวลา
Date: 2026-10-08

## Goal
- เขียน `auto-loop/verify.ps1` ใหม่ให้ตัดสินจาก M1–M4 ใน `auto-loop/GOAL.md`
- ปรับ `run-loop.ps1` ให้ Claude ใช้เครื่องมือได้ทุกตัว รวมถึง WSL, เว็บ และ Codex
  ไม่จำกัดเวลา แต่จับเวลาและเขียนรายงานทุกรอบและทุก job

## Context
- ผู้ใช้สั่ง "เขียนใหม่เลย" (verify) และขอ run-loop แบบเข้าถึงทรัพยากรเต็ม ไม่จำกัดเวลา บันทึกรายงานตลอด
- การเทรนรันใน WSL Ubuntu ที่ `~/RL_Fall` (clone แยกจาก `C:\RL_Fall` ตามหลังอยู่ 2 commit) ใช้ venv `~/venvs/rl_fall`
- ผลของ S1 อยู่ใน `results/stage1_v1_0/seed_*/.../survival_curve.json` (มี `update_N.survival`, `step_rate`, `stance_N.feet_drift_m`...)
- `pytest` ของโปรเจกต์รันจาก `/mnt/c/RL_Fall` ด้วย venv ใน WSL ได้ ใช้เวลา ~40 วินาที
- Codex เดิมถูก sandbox บล็อก (`CreateProcessAsUserW failed: 5`)

## Steps
1. ย้ายงานตัวอย่าง BAHTTEXT (`src/`, `tests/`) ไป `auto-loop/examples/bahttext/`
2. `tools/check_goal.py`: ตรวจ M1–M4 จากไฟล์ผลจริง เขียน `reports/goal-status.md`
3. `verify.ps1`: รัน pytest ของโปรเจกต์ใน WSL และ `check_goal.py`
4. `tools/wsl-job.ps1` + `tools/job-wrapper.sh` + `tools/jobs.ps1`: sync โค้ดไป WSL แล้วรัน job แบบ detached
   บันทึกเวลาเริ่ม เวลาจบ ระยะเวลา และ exit code ทุก job
5. `run-loop.ps1`: ทำงานที่ root ของโปรเจกต์บน branch แยก, allowedTools เต็ม, ไม่จำกัดเวลา/รอบโดยค่าเริ่มต้น,
   รอ job ด้วยไฟล์ `WAIT_FOR_JOBS`, เขียน `reports/loop-report.md` และ `reports/iterations.csv`
6. `tools/codex.sh` ใช้ `danger-full-access` ให้ Codex รันคำสั่งได้
7. เขียน `PROMPT.md`, `GOAL.md` (เพิ่มสัญญาไฟล์ผล), `README.md` ใหม่

## How it will be verified
- รัน `verify.ps1` ตอนนี้: pytest ต้องผ่าน และ check_goal ต้องรายงาน M1 ไม่ผ่านด้วยเหตุผลที่ถูก (ยังไม่มี `milestones/m1_runs.json`)
- ทดสอบ check_goal กับ m1_runs.json ชั่วคราวที่ชี้ผล 3 seeds เดิม → ต้องตกเพราะ seed 63002 เท้าเลื่อน 29.8 ซม. และ run เก่ากว่า 8 ต.ค.
- ทดสอบ wsl-job.ps1 ด้วย job สั้น (`sleep 5; echo ok`) ดูว่าบันทึกเวลาและสถานะครบ
- parse `run-loop.ps1` ด้วย PowerShell parser (ไม่รันลูปจริง เพราะเสียเงินและใช้เวลา)

## Risks / assumptions
- เปิดสิทธิ์เต็ม: Claude ในลูปรันคำสั่งอะไรก็ได้ และ Codex ไม่มี sandbox ตามที่ผู้ใช้ขอ
- "ไม่จำกัดเวลา": ตั้ง `-MaxHours 0` และ `-MaxIterations 0` = ไม่จำกัด เป็นค่าเริ่มต้น ยังส่งค่าเองได้
- ลูป commit ลง branch `loop/research` (สร้างจาก HEAD ปัจจุบัน) ไม่ใช่ `curriculum-stage1`
- เกณฑ์ M2 "ไม่ต่ำกว่าอย่างมีนัย" ตีความเป็นต่ำกว่าไม่เกิน 5 จุดเปอร์เซ็นต์
