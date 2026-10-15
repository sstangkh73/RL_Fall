# Plan: เขียนรายงานโครงการฉบับเต็ม (เป็นเล่ม)
Date: 2026-10-11

## Goal
ผู้ใช้ขอ "รายงานเป็นเล่มฉบับเต็ม" ของโครงการ RL Fall หลังลูปผ่าน M1–M4
เสร็จเมื่อมีเอกสารครบบท (บทคัดย่อ, บทนำ, งานที่เกี่ยวข้อง, วิธีการ, ผล, อภิปราย/ข้อจำกัด, แผน S3 + LANTA, สรุป, ภาคผนวก)
และตัวเลขทุกตัวตรงกับไฟล์ผลจริง

## Context
- ฉบับย่อมีอยู่แล้ว: `planning/Evidence_Summary_TH.md` (~4 หน้า ตาม M4)
- แหล่งข้อมูล: `auto-loop/GOAL.md`, `planning/Curriculum_Plan_TH.md`, `planning/LANTA_Compute_Estimate_TH.md`,
  `research/prior_art_review_th.md`, โค้ด `src/rl_fall/env3d.py`, `damage.py`, `train.py`,
  manifest และ `s2_eval*.json` ใน `~/RL_Fall/results/` (WSL)

## Steps
1. สร้างเอกสารเป็น Claude Docs (ตาม quickstart ของ Artifact; ผู้ใช้ไม่ได้ระบุ .docx)
2. อ่านแหล่งข้อมูลทั้งหมด ดึงตัวเลขจากไฟล์ผลจริงใน WSL
3. เขียนทีละบท แล้ววาดกราฟ 3 รูป (survival curve S1, damage แยก impulse, damage แยกส่วนร่างกาย)
4. ตรวจกราฟด้วย screenshot

## How it will be verified
เทียบตัวเลขในเอกสารกับ `s2_eval.json`, `s2_eval_n48.json`, manifest และตารางใน Curriculum_Plan_TH.md

## Risks / assumptions
- รูปแบบ: เลือก Claude Docs (ส่งออกเป็น PDF/Word ได้ภายหลัง) แทนการถาม
- ภาษาไทย เขียนให้อาจารย์ที่ปรึกษาและผู้พิจารณา LANTA อ่าน
