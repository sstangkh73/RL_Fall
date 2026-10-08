# Progress

ความจำของ AI ระหว่างรอบ AI จะเขียนต่อท้ายไฟล์นี้ทุกรอบ

## สถานะเริ่มต้น (8 ต.ค. 2026, เขียนโดยคน + Claude ก่อนเริ่มลูป)

- ผลทำซ้ำ 3 seeds ของ recipe v1.0 (7 ต.ค.) ยังไม่ผ่าน M1:
  seed 63001 เท้าเลื่อน 7.9 ซม., 63002 เท้าเลื่อน 29.8 ซม., 63003 เท้าเลื่อน 8.4 ซม. (เกณฑ์ ≤ 8 ซม.)
- สาเหตุของ 63002 ที่บันทึกไว้: บทลงโทษท่ายืนรวมถูกจำกัดไว้ที่ 1.0 ต่อ step (ดูส่วน "Natural-stance rule" ใน `src/rl_fall/env3d.py`)
  พอเท้าเลื่อนเกิน ~18 ซม. บทลงโทษก็ไม่เพิ่มอีก
- ขั้น A, B และ CP ของ recipe (`scripts/run_stage1_v1_recipe.sh`) ไม่ใช้กติกายืนสบาย ถ้าแก้แค่ส่วนนั้น
  อาจเริ่มใหม่ที่ R1 จาก checkpoint CP เดิมใน `~/RL_Fall/results/stage1_v1_0/seed_*/push_0.12_hard0.5_posture2.0_cp10/` ได้ (ต้องตรวจสอบก่อน)
- clone ใน WSL (`~/RL_Fall`) ตามหลัง `C:\RL_Fall` แต่ `wsl-job.ps1` copy โค้ดให้ก่อนรันทุกครั้ง

## Log

### รอบ 2026-10-08 02:15
- **ทำอะไร (M1, ทำเอง):** เพิ่ม `posture_version=3` ใน `src/rl_fall/env3d.py`
  - เท้าเลื่อนเกิน dead zone 8 ซม. คิดคะแนนแบบเชิงเส้น ไม่ใช่กำลังสองแบบ v2 จึงมีต้นทุนตั้งแต่ 9 ซม.
    ส่วน crouch และ lean ยังเป็นกำลังสองแบบเดิม
  - penalty = reward_ก่อนหัก × s/(s+0.5) โดย s = weight × score ต้นทุนจึงเพิ่มขึ้นทุกเซนติเมตร
    แต่ไม่ถึง 100% ของ reward ทำให้ reward ต่อ step ยังเป็นบวกเสมอ
    (เทียบกับ v2: ที่ 30 ซม. v3 หักประมาณ 1.2 ส่วน v2 หัก 1.0 คงที่ตั้งแต่ 18 ซม.)
  - ไม่แก้ v1/v2 เพราะต้องให้ผลเดิมทำซ้ำได้ เพิ่ม choice 3 ใน `train.py --posture-version`
  - เพิ่ม test `test_v3_posture_cost_keeps_growing_past_the_dead_zone_and_reward_stays_positive`
    ใน `tests/test_balance.py` ใช้ drift 5, 9, 12, 18, 30, 50, 100 ซม. แล้วเช็กว่า penalty เพิ่มขึ้นทุกจุด, reward > 0 และที่ 30 ซม. penalty > 1.0
  - `scripts/run_stage1_v1_recipe.sh`: R1/R2 เปลี่ยนเป็น v3 และใช้ TAG `natural3_r1`/`natural3_r2` ส่วน run v2 เดิมยังเก็บไว้
    A/B/CP complete แล้วทั้ง 3 seeds (ตรวจ manifest แล้ว) จึงข้ามขั้นนั้นและเริ่ม R1 จาก CP checkpoint เดิม
- **verify:** pytest ผ่านทั้งหมด ส่วน goal ยัง FAIL (ยังไม่มี milestone files)
- **job ที่สั่ง:**
  - `20261008-021340-m1v3_a` = `bash scripts/run_stage1_v1_recipe.sh 63002 63001`
  - `20261008-021342-m1v3_b` = `bash scripts/run_stage1_v1_recipe.sh 63003`
  - คาดว่าใช้ ~1–1.5 ชม. ต่อ seed (R1+R2 = 400 updates × 16,384 ≈ 6.6M transitions ที่ ~2,400/s ≈ 46 นาที
    บวก survival eval) job a มี 2 seeds จึงคาดว่าใช้ ~2–3 ชม.
- **job ที่จบ:** ไม่มี
- **ปัญหา:** ยังไม่มี ข้อสังเกต: seed 63003 (v2) เท้าเลื่อน 8.4 ซม. ซึ่งอยู่แค่ขอบ dead zone
  ใน v2 ส่วนนี้แทบไม่มีต้นทุนเพราะคิดแบบกำลังสอง ส่วน v3 คิดแบบเชิงเส้นจึงน่าจะดันให้ต่ำกว่า 8 ซม.
  ถ้า median ยังเกิน 8 ซม. อาจต้องเริ่มคิดต้นทุนก่อนถึง 8 ซม. หรือเพิ่ม weight
- **งานถัดไป:** พอ job จบ ให้อ่าน `survival_curve.json` ของ run `natural3_r2` ทุก seed (stance_200, update_200 ที่ 0.08/0.10/0.12)
  บันทึกลง `planning/Curriculum_Plan_TH.md` ถ้าผ่านให้เขียน `auto-loop/milestones/m1_runs.json`
  ระหว่างรอ ถ้ามีรอบว่าง ให้เตรียม M2 ได้ (env S2: weighted damage, รันต่อหลังล้ม และสคริปต์ s2_eval)

### รอบ 2026-10-08 09:25
- **job ที่จบ:**
  - `20261008-021342-m1v3_b` (63003) ใช้ 5:01 ชม., `20261008-021340-m1v3_a` (63002+63001) ใช้ 6:40 ชม. ทั้งคู่ exit 0
    (รันพร้อมกันจึงช้า ช่วงที่ 63001 รันเดี่ยว R1 47 นาที R2 45 นาที)
  - ผล v3 (R2 update 200): drift 8.0 / 10.2 / 12.1 ซม. (63001/63002/63003), รอดที่ 0.10 = 71/62/83% (เฉลี่ย 72% ผ่าน),
    step rate 0.08→0.12 เพิ่มทุก seed (ผ่าน), CoM ลด ≤0.2 ซม., เอียง 3.3–6.3° (ผ่าน) → **M1 ยังไม่ผ่านเพราะ drift**
    บันทึกลง `planning/Curriculum_Plan_TH.md` แล้ว ยังไม่เขียน m1_runs.json
- **วิเคราะห์ (ทำเอง):** เขียน `scripts/diag_stance_drift.py` (พิมพ์ drift ทุก 0.25 วิ ในการวัดท่ายืนแบบไม่มีแรงผลัก)
  พบว่า policy ขยับเท้าไปเรื่อยๆ ตลอดเวลา (~5 ซม. ที่ 1 วิ, ~10 ที่ 2 วิ, ~20 ที่ 3 วิ) ไม่ได้กางขาค้าง
  ต้นเหตุคือ v3 คิดต้นทุนเฉพาะ t < push_start (1–3 วิ) หลังผลักขยับเท้าได้ฟรี และ policy มองไม่เห็นเวลา
- **แก้ (ทำเอง):** `posture_version=4` ใน `env3d.py` ก่อนผลักเหมือน v3 แต่หลังจบแรงผลัก + 1.5 วิ (`NATURAL_SETTLE_S`)
  จะตั้งตำแหน่งเท้าอ้างอิงใหม่ครั้งเดียว แล้วคิดต้นทุนเท้าเลื่อนแบบ v3 (เท้าอย่างเดียว ไม่คิด crouch/lean)
  ช่วงก้าวกู้จึงยังฟรี เพิ่ม choice 4 ใน train.py และ test `test_v4_posture_cost_returns_after_the_push_settles_from_re_anchored_feet`
  ส่วน recipe R1/R2 เปลี่ยนเป็น v4 tag `natural4_r1/r2` (run v3 ยังเก็บไว้)
- **verify:** pytest ผ่านทั้งหมด ส่วน goal ยัง FAIL (ยังไม่มีไฟล์ milestone)
- **job ที่สั่ง:** `20261008-092513-m1v4` = `bash scripts/run_stage1_v1_recipe.sh 63001 63002 63003 && (diag_stance_drift ทั้ง 3 seeds)`
  รันทีละ seed คาดว่าใช้ ~5–5.5 ชม. (3 × (47+47 นาที + eval 10 นาที))
- **ปัญหา/ข้อสังเกต:** ถ้า v4 ยัง drift > 8 ซม. ทางต่อไปคือ (ก) ลด settle เหลือ 1.0 วิ หรือเพิ่ม weight
  (ข) ดูว่าขยับเท้าเพราะยืนทรงตัวไม่อยู่หรือเปล่า ให้เทียบ passive drift ด้วย diag (policy=0)
  ถ้า survival ที่ 0.10 ตกต่ำกว่า 60% แปลว่าต้นทุนหลังผลักไปกดการก้าวกู้หลายก้าว
- **งานถัดไป:** พอ job จบ ให้อ่าน survival_curve.json ของ `natural4_r2` ทุก seed และ drift trace ท้าย log
  ถ้าผ่านเกณฑ์ทั้งหมดให้เขียน `auto-loop/milestones/m1_runs.json` (ใช้ run natural4_r2 ทั้ง 3 seeds) แล้วเริ่ม M2

### รอบ 2026-10-08 13:27
- **job ที่จบ:** `20261008-092513-m1v4` ใช้ 4:01 ชม. (exit 0) รัน 3 seeds ต่อกัน ~80 นาทีต่อ seed (R1 ~38 + R2 ~37 + eval ~6 นาที)
  ผล v4 `natural4_r2` update 200: drift 4.8 / 7.3 / 4.8 ซม., รอดที่ 0.10 = 42 / 67 / 77% (เฉลี่ย 62%),
  step 0.08→0.12 เพิ่มทุก seed, CoM ≤0.2 ซม., เอียง ≤5° → **M1 ผ่าน** (verify ยืนยัน)
  - ข้อแลกเปลี่ยน: รอดลดจาก v3 (0.10: 72→62%, 0.12: 48→31%) 63001 ที่ 0.10 เหลือ 42% เฉลี่ยผ่านแบบเฉียดฉิว
  - บันทึกตาราง v4 ลง `planning/Curriculum_Plan_TH.md` แล้ว และเขียน `auto-loop/milestones/m1_runs.json` (run natural4_r2 ทั้ง 3 seeds)
- **ทำอะไร (M2 เตรียม, ทำเอง):** เขียน `scripts/diag_fall_damage.py` เพื่อดูว่าล้มแล้วเกิด damage จริงไหม
  (ไม่จบ episode เมื่อล้ม รันต่อ 2.5 วิ วัด peak F/tolerance ต่อส่วน + damage + weighted 5/2/1)
  smoke 2 episodes (seed 63001): **damage เล็กมาก** weighted ~0.0005–0.0014 ต่อการล้ม เกือบทั้งหมดมาจาก torso
  (peak F/tol ~1.2–2.1 ที่ impact) ส่วน**ศีรษะไม่เคยถึง tolerance** (peak 0.4–0.76) แขนขวาของ policy บางทีเกิน (ยันพื้น)
  passive ก็ล้มตั้งแต่ 0.08
- **ผลต่อการออกแบบ M2:** ถ้าใช้ damage model เดิมเป็น reward ต้องคูณ scale ใหญ่ (~1e3) ไม่งั้นสัญญาณจมอยู่ใต้ survival bonus
  และ head_damage_share น่าจะเป็น 0 เกือบตลอด (รายงานตามจริง) ทางเลือกที่ต้องตัดสินรอบหน้า:
  (ก) ใช้ damage เดิม × scale เป็นบทลงโทษ ซึ่งตรงกับ eval แต่สัญญาณ sparse
  (ข) เพิ่ม shaping จาก peak F/tol (เช่น Σ w·max(0, F/tol − 0.5)²) แต่ eval ยังใช้ weighted damage เดิม
  เลือก (ก)+(ข) เล็กน้อยน่าจะดีที่สุด ส่วนเกณฑ์ M2 วัดด้วย damage เดิมเสมอ
- **job ที่สั่ง:** `20261008-132923-falldmg2` = diag_fall_damage.py 12 episodes × 4 impulses × (passive + S1) × 3 seeds
  คาดว่าใช้ ~15–30 นาที (`20261008-132911-falldmg` fail ทันทีเพราะเรียก `python` แทน `~/venvs/rl_fall/bin/python` ซึ่งไม่ใช่ปัญหาโค้ด)
- **verify:** pytest ผ่าน, M1 PASS, M2–M4 FAIL (ยังไม่ได้ทำ)
- **งานถัดไป:** อ่านผล falldmg2 แล้วบันทึกลง Curriculum_Plan (ส่วน S2) จากนั้นออกแบบ env S2 ใน `env3d.py`
  (`fall_continue_s`, weighted damage reward, push แบบกู้ได้ ≤0.08 / กู้ไม่ได้ ≥0.15 อย่างละครึ่ง, fine-tune จาก natural4_r2)
  และสคริปต์ `scripts/stage2_eval.py` ที่เขียน s2_eval.json ตามสัญญาใน GOAL.md (ส่วนนี้ส่งให้ Codex ได้)
