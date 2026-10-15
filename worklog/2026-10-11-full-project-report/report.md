# Report: เขียนรายงานโครงการฉบับเต็ม (เป็นเล่ม)
Date: 2026-10-11   Status: Done

## Summary
เขียนรายงานฉบับเต็ม 7 บท + ภาคผนวก 2 ส่วน พร้อมกราฟ 3 รูป เป็น Claude Docs
"รายงานโครงการ RL Fall: หุ่นเรียนรู้เลือกกู้หรือล้ม" https://claude.ai/artifact/YXLxhFMtAQ2XCSqYSKjjGm
ระหว่างดึงตัวเลขพบข้อมูลสำคัญที่ฉบับย่อไม่ได้เปิดเผย (ด้านล่าง) และใส่ไว้ในบทที่ 5 แล้ว

## What was done
- อ่าน GOAL, Curriculum_Plan (บันทึก S1/S2 ทุกครั้ง), LANTA estimate, prior-art review, damage/env/train code
- ดึงจาก WSL: manifest ของ run S2 สุดท้าย, `s2_eval.json` (per-impulse, per-part), `s2_eval_n48.json`, trend 50/100/150
- เขียนบท: บทคัดย่อ, 1 บทนำ, 2 งานที่เกี่ยวข้อง (ตาราง 9 งาน), 3 วิธีการ (ร่างกาย, damage model, reward, curriculum, PPO, gate),
  4 ผล (M1, M2, diagnostics, การตรวจอิสระ), 5 อภิปราย/ข้อจำกัด, 6 แผน S3 + compute, 7 สรุป, ภาคผนวกไฟล์และวิธีทำซ้ำ
- กราฟ: ภาพ 4.1 survival curve S1, ภาพ 4.2 damage แยก impulse, ภาพ 4.3 damage ลำตัว/แขน
- ไม่ได้แก้ไฟล์ใดในโปรเจกต์ นอกจาก worklog นี้

## Verification
- ตัวเลข M1/M2 ตรงกับ `Evidence_Summary_TH.md` และ `s2_eval.json` ทุก seed
- ตรวจ screenshot กราฟทั้ง 3 รูป แก้ title ภาพ 4.2 (เดิมอ้าง 0.15 ชัดทุก seed ซึ่งไม่จริงกับ 63003) และภาพ 4.3 (4 เท่า → 2.5–4 เท่า)

## Problems / not done
- **ข้อค้นพบใหม่:** config สุดท้ายผ่าน 3/3 เฉพาะที่ 192 episodes; ที่ชุด 48 episodes เดิม (ที่ใช้ตัดสิน config 1–9) ผ่านแค่ 1/3
  (63002 damage > passive, 63003 รอด 81.2 vs 95.8% และ FGU 19.6%) การเปลี่ยนเป็น 192 ถูกบันทึกไว้ก่อนรันจริง แต่ต้องเปิดเผย
- **ข้อค้นพบใหม่:** ลำตัวของ S2 เสียหายมากกว่า passive ใน 2/3 seeds; S2 ชนะ passive เพราะใช้แขนรับแรงน้อยกว่า
- ยังไม่มีวิดีโอ S2 (GOAL M4 กำหนด) และ throughput LANTA ยังไม่ได้วัด
- ช่วงเวลา compute S2 รวม ~40 ชม. เป็นผลรวมจากเวลา job ใน Curriculum_Plan โดยประมาณ

## Next steps
- render วิดีโอ S2, ใส่ตาราง 5.1/5.2 ลง Evidence_Summary_TH.md, ประเมินบน scenario ชุดใหม่พร้อม CI
