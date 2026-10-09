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

### รอบ 2026-10-08 13:38
- **job ที่จบ:** `20261008-132923-falldmg2` ใช้ 2:31 นาที (exit 0) บันทึกตารางลง `planning/Curriculum_Plan_TH.md` ส่วน 5 แล้ว
  weighted damage ต่อการล้มของปล่อยตัวอยู่ที่ 0.0015–0.0023 ส่วน S1 อยู่ที่ 0.0009–0.0029 (มักต่ำกว่าปล่อยตัว)
  เกือบทั้งหมดมาจากลำตัว ศีรษะไม่เคยถึง tolerance (head share น่าจะเป็น ~0) ส่วน passive ให้ผลเหมือนกันทุก seed เพราะใช้ scenario เดียวกัน
- **ทำอะไร (M2, ทำเอง เพราะเป็นการออกแบบ reward):** เพิ่ม S2 ใน `src/rl_fall/env3d.py` (ทุกอย่างปิดไว้เป็นค่าเริ่มต้น ผล S1 เดิมจึงไม่เปลี่ยน)
  - `fall_continue_s`: ล้มแล้วไม่จบ episode รันต่อตามเวลาที่กำหนด และ `fallen` latch ไว้ (ลุกได้ก็ไม่ได้โบนัสคืน)
  - `damage_weight`: โทษ = weight × Σ(5,2,1,1,1,1)·damage_increment ต่อ step (`S2_DAMAGE_WEIGHTS`)
    info มี `weighted_damage_increment` และ `reward_damage_penalty` ด้วย
  - `train.py` เพิ่ม `--fall-continue-s`, `--damage-weight` และ stage `S2_recover_or_fall` ส่วน `run_stage1.sh` เพิ่ม env
    `FALL_CONTINUE`, `DAMAGE_W`, `OUT_ROOT`, `STAGE`
  - `scripts/run_stage2_pilot.sh`: fine-tune จาก natural4_r2 200 updates, push กู้ได้ U(0,0.08) และกู้ไม่ได้ U(0.15,0.25) อย่างละครึ่ง,
    รันต่อ 2.5 วิหลังล้ม, DAMAGE_W=10000 ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000/3d_*`
  - test ใหม่ `test_s2_fall_runs_on_and_charges_weighted_damage`
  - smoke 2 updates: ~1,800 transitions/s, โทษ damage ~−400 ต่อ update (~20 ต่อการล้ม) ต่อ reward ยืน ~16,000
- **เหตุผลที่เลือก DAMAGE_W=10000:** damage ต่อการล้ม ~0.0015 ทำให้เสีย ~15 reward ซึ่งมีนัยเมื่อเทียบกับ reward หลังล้ม (0)
  แต่น้อยกว่าโบนัสยืนที่เสียไปเมื่อล้มมาก การยืนจึงดีกว่าล้มเสมอ (ไม่สร้าง false give-up)
  ยังไม่ใส่ shaping F/tol เพราะแรงที่เท้าตอนยืนจะโดนคิดไปด้วย
- **verify:** pytest ผ่าน, M1 PASS, M2–M4 FAIL (ยังไม่มีผล)
- **job ที่สั่ง:** `20261008-133651-s2pilot` = `bash scripts/run_stage2_pilot.sh 63001 63002 63003`
  คาดว่าใช้ ~2–2.5 ชม. (3 × 200 updates ที่ ~1,800/s ≈ 30 นาที + eval checkpoint ต่อ seed)
- **ปัญหา:** ใน `wsl.exe -- bash -lc '...'` ตัวแปร shell (`$S1`) ถูกแทนค่าเป็นค่าว่างก่อนถึง bash ให้ใส่ path ตรงๆ หรือเรียกผ่านสคริปต์
- **งานถัดไป (ระหว่างรอ job):** ส่งให้ Codex เขียน `scripts/stage2_eval.py` ที่เขียน `s2_eval.json` ตามสัญญาใน GOAL.md
  - ใช้ scenario คู่กัน (seed เดียวกัน) สำหรับ S2, S1 (natural4_r2 update 200) และปล่อยตัว รันต่อ 2.5 วิหลังล้ม แล้ววัด weighted damage
    (ดูวิธีจาก `scripts/diag_fall_damage.py`)
  - กลุ่มกู้ได้: impulse 0.05 กับ 0.08 อย่างละ 24 (รวม 48), กลุ่มกู้ไม่ได้: 0.15/0.20/0.25 อย่างละ 16 (รวม 48)
  - false_give_up = สัดส่วนของ scenario กู้ได้ที่ S1 รอดแต่ S2 ล้ม (เทียบกับจำนวนที่ S1 รอด), head_damage_share = head damage×5 / weighted รวม (กลุ่มกู้ไม่ได้ของ S2)
  - ตอนประเมินต้องสร้าง env ด้วย `fall_continue_s=2.5` แต่ไม่ต้องใส่ damage_weight (ไม่มีผลต่อการวัด)
  พอ job จบให้รัน eval ทั้ง 3 seeds แล้วเขียน `auto-loop/milestones/m2_summary.json` เฉพาะเมื่อมีผลจริง
  ถ้า S2 damage ไม่ต่ำกว่า S1 ให้ลอง shaping F/tol เฉพาะ geom ที่ไม่ใช่เท้า หรือเพิ่ม DAMAGE_W

### รอบ 2026-10-08 13:45
- **ทำอะไร (M2, Codex + ทำเอง):** Codex เขียน `scripts/stage2_eval.py` + `tests/test_stage2_eval.py` (spec อยู่ใน `worklog/codex_task_stage2_eval.md`)
  ตรวจ diff แล้ว: scenario คู่กัน S2/S1/passive, กลุ่มกู้ได้ 0.05/0.08 ×24, กู้ไม่ได้ 0.15/0.20/0.25 ×16, `fall_continue_s=2.5`, ไม่ใส่ damage_weight,
  weighted damage เฉลี่ยทุก episode (รวมที่ไม่ล้ม), false_give_up และ head_damage_share ตามนิยามใน GOAL.md เขียน `<S2 run>/s2_eval.json`
  smoke (S1 เทียบกับตัวเอง, scale 0.1): ผล S2 = S1 ตรงกันทุกค่า (deterministic) ~31 วินาทีต่อ 30 episodes → เต็ม 288 episodes ~5 นาที/seed (ถ้าไม่แย่ง CPU)
  ทำเอง: `scripts/run_stage2_eval.sh` (หา run S2 ล่าสุดกับ natural4_r2 ของแต่ละ seed แล้วเรียก eval)
- **verify:** pytest ผ่าน (รวม test ใหม่), M1 PASS, M2–M4 FAIL (ยังไม่มีผล)
- **job ที่กำลังรัน:** `20261008-133651-s2pilot` (สั่งรอบก่อน คาดว่าใช้ ~2–2.5 ชม.)
- **job ที่สั่ง:** `20261008-134435-s2eval` = `while pgrep -f run_stage2_pilot.sh; do sleep 60; done; bash scripts/run_stage2_eval.sh 63001 63002 63003`
  รอ pilot จบก่อนแล้วค่อย eval คาดว่าใช้ ~15–30 นาทีหลัง pilot จบ
- **job ที่จบ:** ไม่มี
- **ปัญหา:** คำสั่งเดียวกันใน Bash tool ที่มี heredoc + `{"` ถูก block ("expansion obfuscation") ให้เขียน prompt Codex ลงไฟล์ด้วย Write แล้วสั่ง Codex ให้อ่านไฟล์นั้น
- **งานถัดไป:** อ่าน log ของ s2pilot (updates.csv: damage penalty, survival) และ `s2_eval.json` ทั้ง 3 seeds แล้วบันทึกตารางลง Curriculum_Plan ส่วน 5
  ถ้าผ่านเกณฑ์ (S2 รอดกลุ่มกู้ได้ ≥ S1−5pp, damage กลุ่มกู้ไม่ได้ < S1 และ < passive, false give-up ≤10%) ให้เขียน `auto-loop/milestones/m2_summary.json`
  (run_dir = run S2, eval_file = s2_eval.json ทั้ง 3 seeds ห้ามเลือก seed) ถ้าไม่ผ่าน: ลอง shaping F/tol เฉพาะ geom ที่ไม่ใช่เท้า หรือเพิ่ม DAMAGE_W
  ระหว่างรอ ทำ M3 ได้ (sbatch ใน `scripts/lanta/`, throughput จาก resources.jsonl)

### รอบ 2026-10-08 15:40
- **job ที่จบ:**
  - `20261008-133651-s2pilot` ใช้ 1:53 ชม. (exit 0) ~38 นาทีต่อ seed
  - `20261008-134435-s2eval` ใช้ 1:54 ชม. (exit 0) ส่วนใหญ่เป็นเวลารอ pilot ตัว eval จริงใช้ ~3 นาทีต่อ seed
  - ผล S2 update 200: damage บนแรงผลักที่กู้ไม่ได้ต่ำกว่า S1 และปล่อยตัวทุก seed (ผ่าน)
    แต่รอดบนแรงผลักที่กู้ได้ 83/69/69% เทียบกับ S1 88/96/96% และ false give-up 11.9/28.3/30.4% → **M2 ไม่ผ่าน**
    head share 0/0/1.1% บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว ยังไม่เขียน m2_summary.json
- **ทำอะไร (ทำเอง):** วิเคราะห์ updates.csv (โทษ damage ลด ~−600→−250 ส่วนการล้มไม่มีแนวโน้มชัด)
  เขียน `scripts/run_stage2_eval_trend.sh` เพื่อประเมิน checkpoint ก่อนหน้า และเขียนผลเป็น `s2_eval_update_<N>.json` (ไม่ทับ s2_eval.json)
  (`worklog/s2_curves.sh` = สคริปต์ดู updates.csv ทุก 20 updates)
- **job ที่สั่ง:** `20261008-154040-s2trend` = `bash scripts/run_stage2_eval_trend.sh 63001 63002 63003` (update 0/50/100/150)
  คาดว่าใช้ ~35–40 นาที (12 evals × ~3 นาที)
- **verify:** ไม่ได้แก้โค้ด src (เพิ่มแค่ shell script) ผลล่าสุดคือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **ปัญหา:** S2 แลกการรอดบนแรงผลักที่กู้ได้ไปกับ damage ที่ลดลง และ heredoc ใน Bash tool ถูก parser ปฏิเสธ ให้ใช้ Edit/Write แทน
- **งานถัดไป:** อ่าน `s2_eval_update_*.json` ทั้งหมด แล้วบันทึกเป็นตารางแนวโน้มลง Curriculum_Plan ส่วน 5
  - ถ้า update 0 (S1 weights ที่ยังไม่ได้เทรนด้วย reward ใหม่) false give-up ต่ำ แต่เพิ่มขึ้นตาม update แปลว่าเป็นผลจาก reward:
    ลอง DAMAGE_W ต่ำลง (เช่น 3000) และ/หรือขยายช่วงกู้ได้เป็น U(0, 0.12) ให้ตรงกับ S1 (สมมติฐาน ค)
  - ถ้าตกตั้งแต่ update 50 แล้วคงที่ แปลว่าเป็นช็อกจาก critic (สมมติฐาน ก): ลอง learning rate ต่ำลง หรือ warm-up critic ก่อน
  - ถ้ามี checkpoint ที่ผ่าน gate ห้ามหยิบมาใช้เฉพาะตัวนั้น ต้องตั้งกฎล่วงหน้า (เช่น update คงที่ทุก seed) แล้วเทรนใหม่
  - ระหว่างรอ ทำ M3 ได้ (sbatch + compute estimate)

### รอบ 2026-10-08 16:18
- **job ที่จบ:** `20261008-154040-s2trend` ใช้ 35:24 นาที (exit 0) ประเมิน checkpoint S2 update 0/50/100/150 ทั้ง 3 seeds
  - update 0 = S1 ตรงกันทุกค่า (FGU 0%) false give-up โผล่ตั้งแต่ update 50 (6.5–14.3%) แล้วแกว่งไม่เป็นทิศทาง (2.2–30.4%)
    damage กลุ่มกู้ไม่ได้ลดตั้งแต่ update 50 ไม่มี checkpoint ไหนผ่าน gate ครบ 3 seeds บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว
- **วิเคราะห์ (ทำเอง):** `scripts/diag_s2_obsnorm.py` + `scripts/run_diag_s2_obsnorm.sh` สลับ weights กับ VecNormalize ของ S1/S2 (63003, 63001)
  S1 weights + S2 norm ยังรอด 92% แต่ S2 weights + S1 norm ตก (65/54%) → **ต้นเหตุคือ weights ไม่ใช่สถิติ obs** (return std ก็ไม่เปลี่ยน 42.4→42.2)
  reward (gamma 0.99, ยืน ~1.5/step ≈ 150 เทียบ damage ~15 ต่อการล้ม) ไม่ได้จูงใจให้ยอมล้ม จึงสรุปว่าน่าจะเป็นความไม่เสถียรของ fine-tune
  จาก critic ของ S1 ที่ไม่เคยเห็นสถานะหลังล้ม (สมมติฐาน ก) ข้อสังเกต: obs มี `remaining` (เวลาที่เหลือ) อยู่แล้ว policy จึงรู้เวลา
- **แก้ (ทำเอง):** `train.py` เพิ่ม `--critic-warmup-updates N` (+ `set_actor_trainable`) แช่แข็ง policy_net/action_net/log_std ใน N updates แรก
  (requires_grad=False ทำให้ Adam ข้ามพารามิเตอร์เหล่านั้น) บันทึก `critic_warmup_updates` ลง manifest
  `run_stage1.sh` เพิ่ม env `CRITIC_WARMUP`, `run_stage2_pilot.sh` เพิ่ม `CRITIC_WARMUP` (tag `_cw<N>`; ถ้าเป็น 0 tag เดิมไม่เปลี่ยน)
  เพิ่ม `scripts/run_stage2_critic_warmup.sh` (เทรน + eval update 200 + trend 50/100/150) และ test `tests/test_critic_warmup.py`
  (actor ไม่เปลี่ยนใน update ที่ warm-up แต่ critic เปลี่ยน แล้ว actor กลับมาเทรนต่อ)
- **verify:** pytest ผ่าน 52 tests, M1 PASS, M2–M4 FAIL (ยังไม่มีผล)
- **job ที่สั่ง:** `20261008-162754-s2cw25` = `bash scripts/run_stage2_critic_warmup.sh 63001 63002 63003`
  (CRITIC_WARMUP=25, DAMAGE_W=10000 ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_cw25/`)
  คาดว่าใช้ ~2.5 ชม. (3 × ~38 นาที + eval 3 × 3 นาที + trend 9 × 3 นาที)
- **ปัญหา:** `wsl.exe -- bash -lc '...'` จาก Bash tool ก็ยังแทนค่า `$S` เป็นค่าว่าง ต้องใช้สคริปต์ .sh เสมอ
  ถ้าจะรันสคริปต์ใหม่ที่ยังไม่ได้ sync ไป `~/RL_Fall` ให้ cp จาก /mnt/c ก่อน (ผลอยู่ใน ~/RL_Fall/results)
- **งานถัดไป:** อ่าน `s2_eval.json` และ `s2_eval_update_*.json` ของ `s2_dmg10000_cw25` แล้วเทียบกับ `s2_dmg10000` ใน Curriculum_Plan ส่วน 5
  - ถ้าผ่าน gate ทั้ง 3 seeds ที่ update 200 → เขียน `auto-loop/milestones/m2_summary.json` (run cw25 ทั้ง 3 seeds)
  - ถ้า false give-up ยังแกว่ง: ลอง learning rate fine-tune ต่ำลง (เช่น 3e-5 ตอนนี้ CURRICULUM_PPO ใช้ 1e-4)
    และ/หรือขยายช่วงกู้ได้เป็น U(0, 0.10) (สมมติฐาน ค) ทีละอย่าง
  - ระหว่างรอ job ทำ M3 ได้ (sbatch ใน `scripts/lanta/` + throughput จาก resources.jsonl / manifest steady_transitions_per_second)

### รอบ 2026-10-08 19:00
- **job ที่จบ:** `20261008-162754-s2cw25` ใช้ 2:29 ชม. (exit 0)
  ผล update 200: รอดกลุ่มกู้ได้ 70.8 / 87.5 / 70.8% (S1 87.5 / 95.8 / 95.8%), false give-up 33.3 / 13.0 / 28.3%,
  damage กลุ่มกู้ไม่ได้ต่ำกว่า S1 และปล่อยตัวทุก seed → **M2 ไม่ผ่าน** trend 50/100/150 ยังแกว่ง (FGU 4.3–17.4%)
  สรุปว่า critic warm-up ไม่ใช่ทางแก้ (สมมติฐาน ก ตกไป) บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว ยังไม่เขียน m2_summary.json
- **ทำอะไร (ทำเอง):** เพิ่ม `--learning-rate` ใน `train.py` (`set_learning_rate` จะ override LR ของ checkpoint ที่โหลดมาหรือที่ resume
  และบันทึก `learning_rate_override` ลง manifest) เพิ่ม env `LR` ใน `run_stage1.sh` และ `run_stage2_pilot.sh` (tag `_lr<LR>`)
  เพิ่มสคริปต์ใหม่ `scripts/run_stage2_lr.sh` (LR=3e-5, ไม่มี warm-up, เทรน + eval 200 + trend 50/100/150)
  และ test `test_learning_rate_override_applies_to_a_loaded_checkpoint`
- **verify:** pytest ผ่านทั้งหมด, M1 PASS, M2–M4 FAIL
- **job ที่สั่ง:** `20261008-190041-s2lr3e5` = `bash scripts/run_stage2_lr.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_lr3e-5/` คาดว่าใช้ ~2.5 ชม.
- **ปัญหา:** M2 ไม่ผ่านมา 2 รอบแล้ว (s2_dmg10000, cw25) ถ้ารอบ LR ยังไม่ผ่าน ต้องขอความเห็นที่สองจาก Codex (วิเคราะห์อย่างเดียว)
  ข้อสังเกต: ประเมิน 48 episodes และ S1 รอด ~42–46 ตัว FGU 1 episode ≈ 2.2 จุด จึงมี noise สูง
- **งานถัดไป:** ระหว่างรอ job (ห้ามสั่งเทรนซ้อน) ให้ทำ M3: `scripts/lanta/*.sbatch` (recipe S1 + S2 บน CPU node),
  throughput จาก manifest/resources.jsonl, ร่าง `planning/LANTA_Compute_Estimate_TH.md` (ยังไม่เขียน m3_compute.json จนกว่า transitions S2 to gate จะรู้ค่า
  หรือให้ระบุชัดว่าเป็นค่าประมาณ) พอ job จบ ให้อ่าน s2_eval*.json ของ `lr3e-5` แล้วเทียบกับ 2 run ก่อนหน้า
  ถ้ายังไม่ผ่าน → ขอ Codex วิเคราะห์ จากนั้นลองสมมติฐาน (ค) ขยายช่วงกู้ได้เป็น U(0, 0.12) หรือ DAMAGE_W 3000

### รอบ 2026-10-08 19:10
- **ทำอะไร (M3 ร่าง, ทำเอง):** ระหว่างรอ `s2lr3e5`
  - ดึง throughput จาก manifest ทุก run (`worklog/m3_throughput.sh` + `worklog/m3_manifest.py`) ได้ว่ารันเดี่ยว S1 ~1,930 t/s และ S2 ~1,750–1,840 t/s
    ถ้ารัน 2 job ซ้อนกันจะเหลือ ~480 t/s ต่อ job
  - `scripts/lanta/bench_throughput.sbatch` (K runs พร้อมกัน แล้วรวม throughput), `s1_recipe.sbatch`, `s2_pilot.sbatch`
    (ทุกไฟล์ใช้ `-p compute -N 1 -c 128 -A <project-account>` ยังไม่ได้ submit) และ `bash -n` ผ่านทั้งหมด
  - `planning/LANTA_Compute_Estimate_TH.md` (ร่าง): S1 ถึง gate ใช้ 1,050 updates = 17.2M ต่อ seed, S2 สมมติ 400 updates,
    S3 สมมติ 800 updates ×2 สำหรับช่วงพัฒนา, 56 runs ≈ 1,046M transitions, สมมติ 10 runs × 1,200 t/s ต่อ node → **~31 node-hours**
    เสนอขอ ~100 node-hours แหล่งอ้างอิง LANTA: top500.org/system/180125 และ ThaiSC docs
  - **ยังไม่เขียน m3_compute.json** เพราะ S2 ยังไม่ผ่าน gate (ตัวเลข S2 ยังเป็นค่าสมมติ) ต้องแก้ข้อ 2–5 ในเอกสารหลัง M2 ผ่าน
  - Curriculum_Plan ข้อ 7: บันทึกว่าลดเหลือ 10 runs ต่อ node และชี้ไปที่เอกสารนี้
- **verify:** ไม่ได้รัน เพราะไม่ได้แก้ src/tests (แก้แค่ sbatch และ doc) และไม่อยากแย่ง CPU กับ job เทรน ผลล่าสุดคือ pytest ผ่าน, M1 PASS
- **job ที่กำลังรัน:** `20261008-190041-s2lr3e5` (สั่งรอบก่อน คาดว่าใช้ ~2.5 ชม.) **job ที่สั่ง/จบ:** ไม่มี
- **ปัญหา:** `wsl.exe ... 2>&1 | head` และ `MSYS_NO_PATHCONV=...` ถูกขอ permission ให้ใช้ `wsl.exe -d Ubuntu -- bash -lc "bash /mnt/c/RL_Fall/<script>.sh"` แทน
- **งานถัดไป:** อ่าน s2_eval*.json ของ `s2_dmg10000_lr3e-5` แล้วบันทึกลง Curriculum_Plan ส่วน 5
  ถ้าผ่าน → m2_summary.json แล้วแก้ตัวเลข S2 ในเอกสาร M3 แล้วเขียน m3_compute.json
  ถ้าไม่ผ่าน (ครั้งที่ 3) → ขอ Codex วิเคราะห์อย่างเดียว (ส่ง FGU/รอด ทั้ง 3 run + สิ่งที่ลองไปแล้ว) แล้วลอง U(0, 0.12) หรือ DAMAGE_W 3000

### รอบ 2026-10-08 22:05
- **job ที่จบ:** `20261008-190041-s2lr3e5` ใช้ 3:03 ชม. (exit 0, เทรน ~47 นาทีต่อ seed)
  ผล update 200: รอดกลุ่มกู้ได้ 87.5 / 33.3 / 75.0% (S1 87.5 / 95.8 / 95.8%), FGU 9.5 / 65.2 / 23.9%,
  damage กลุ่มกู้ไม่ได้ < S1 และ < ปล่อยตัวทุก seed → **M2 ไม่ผ่าน (ครั้งที่ 3)** trend 50/100/150 FGU 4.3–47.8% แกว่งเหมือนเดิม
  บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว สรุปว่า LR ต่ำลงไม่ช่วย
- **ทำอะไร (ทำเอง):** เขียน `scripts/run_stage2_control.sh` เป็น control ที่ใช้ S2 recipe เดิมทุกอย่าง (lr 1e-4) แต่ **DAMAGE_W=0** (tag `s2_dmg0`)
  แล้ว eval 200 + trend 50/100/150 เพื่อแยกว่า FGU มาจาก damage reward หรือเป็นแค่ drift จากการเทรน PPO ต่อ / push mix
  (ถ้า control ก็มี FGU 10–30% → ต้นเหตุไม่ใช่ damage ทางแก้ควรเป็น anchor ไปที่ S1 (KL/BC บนแรงผลักที่กู้ได้) หรือขยายช่วงกู้ได้
  ถ้า control FGU ต่ำ → ต้นเหตุคือ damage term ให้ลอง DAMAGE_W 3000)
- **ขอความเห็นที่สองจาก Codex (ข้อ 8):** เขียน prompt ไว้ที่ `worklog/codex_task_s2_fgu_analysis.md` (วิเคราะห์อย่างเดียว)
  **แต่ Codex ติด usage limit ใช้ได้อีกทีหลัง 2026-10-09 02:32** จึงยังไม่ได้คำตอบ
  ตรวจเองแล้ว: env3d.py:574/639 การหมดเวลานับเป็น terminated (ไม่ bootstrap) และ obs มี `remaining` จึงสอดคล้องกัน ไม่พบ bug ชัด
- **verify:** ไม่ได้รัน (เพิ่มแค่ shell script ไม่ได้แก้ src/tests) ผลล่าสุดคือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **job ที่สั่ง:** `20261008-220533-s2ctrl` = `bash scripts/run_stage2_control.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg0/` คาดว่าใช้ ~2.5–3 ชม.
- **งานถัดไป:** อ่าน s2_eval*.json ของ `s2_dmg0` แล้วบันทึกลง Curriculum_Plan ส่วน 5 (เทียบ FGU กับ 3 run ก่อนหน้า)
  ถ้าเวลาเลย 02:32 แล้ว ให้รัน Codex ใหม่ด้วย `bash auto-loop/tools/codex.sh "Read the file worklog/codex_task_s2_fgu_analysis.md ..."`
  (เพิ่มผล control ลงในไฟล์ prompt ก่อน) แล้วเลือกทางแก้ตามผล control ข้างบน

### รอบ 2026-10-08 23:55
- **job ที่ตาย:** `20261008-220533-s2ctrl` (jobs.ps1 ขึ้น stale) เพราะ WSL VM รีสตาร์ต (uptime 2 นาทีตอน 23:53)
  heartbeat สุดท้ายตอน 23:39 และ updates.csv ของ 63002 หยุดที่ update 74 ตอน 23:40 ไม่เหลือ process ใน WSL แล้ว
  seed 63001 เทรนครบ 200 updates แล้ว (22:05–23:09 ใช้ ~64 นาที) แต่ยังไม่ได้ eval ไม่รู้ว่าทำไม VM รีสตาร์ต
  (job ก่อนหน้ารันได้นานหลายชั่วโมงโดยไม่มีปัญหา) ถ้าเกิดซ้ำต้องดูว่า Windows sleep/update หรือ verify ทำให้ WSL shutdown หรือไม่
- **ทำอะไร (ทำเอง):** สั่งคำสั่งเดิมใหม่ (สคริปต์รันซ้ำได้: ข้าม 63001 ที่เสร็จแล้ว และ 63002 resume จาก checkpoint_update_75) ตรวจใน log แล้วว่า `--resume` ถูก run
  สคริปต์ตรวจสถานะ: `worklog/check_s2ctrl.sh`
- **job ที่สั่ง:** `20261008-235337-s2ctrl2` = `bash scripts/run_stage2_control.sh 63001 63002 63003`
  คาดว่าใช้ ~2.3 ชม. (63002 อีก 125 updates ~40 นาที + 63003 ~60 นาที + eval 3×3 นาที + trend 9×3 นาที)
- **job ที่จบ:** ไม่มี (s2ctrl ตายกลางทาง ไม่มีผล)
- **verify:** ไม่ได้แก้ src/tests ผลล่าสุด (23:52) คือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **งานถัดไป:** เหมือนรอบ 22:05 คืออ่าน s2_eval*.json ของ `s2_dmg0` แล้วบันทึกลง Curriculum_Plan ส่วน 5 (ใส่เวลา job s2ctrl + s2ctrl2)
  จากนั้นรัน Codex วิเคราะห์ (หลัง 02:32) ด้วย `worklog/codex_task_s2_fgu_analysis.md` + ผล control แล้วเลือกทางแก้
  (control FGU สูง → anchor ไปที่ S1 / ขยายช่วงกู้ได้; control FGU ต่ำ → DAMAGE_W 3000)

### รอบ 2026-10-09 02:14
- **job ที่จบ:** `20261008-235337-s2ctrl2` ใช้ 2:19 ชม. (exit 0) control `s2_dmg0` (DAMAGE_W=0) ครบ 3 seeds
  update 200: รอดกลุ่มกู้ได้ 66.7 / 79.2 / 93.8%, FGU 28.6 / 19.6 / 6.5%, damage กลุ่มกู้ไม่ได้ 0.00094 / 0.00197 / 0.00147
  trend 50/100/150 FGU 2.2–26.2% → **ไม่มี damage reward ก็ยังมี FGU แกว่งเท่าเดิม ต้นเหตุไม่ใช่ damage term**
  (damage term ลด damage ได้จริง: dmg10000 ลดทุก seed ส่วน dmg0 ลดแค่ 63001) บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว
- **ทำอะไร (ทำเอง):** `scripts/run_s1_fgu_noise_floor.sh` เทียบ checkpoint S1 update 125/150/175 กับ S1 update 200 ด้วย `stage2_eval.py`
  (S1 run อยู่ทั้งช่อง s2 และ s1) เพื่อวัด noise floor ของ FGU ที่เกิดจาก drift ปกติของการเทรน
- **job ที่สั่ง:** `20261009-021413-s1fgufloor` = `bash scripts/run_s1_fgu_noise_floor.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/fgu_noise_floor/seed_*/s1_update_<N>_vs_200.json` คาดว่าใช้ ~35 นาที (9 evals × ~3.7 นาที)
- **verify:** ไม่ได้แก้ src/tests (เพิ่มแค่ shell script) ผลล่าสุด (02:13) คือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **Codex:** ยังติด usage limit ถึง 02:32 จึงยังไม่ได้ขอความเห็นที่สอง
- **งานถัดไป:** อ่านผล noise floor แล้วบันทึกลง Curriculum_Plan ส่วน 5 จากนั้นรัน Codex วิเคราะห์อย่างเดียว
  (`worklog/codex_task_s2_fgu_analysis.md` + เพิ่มผล control dmg0 และ noise floor ลงไปก่อน)
  - noise floor สูง (S1 เทียบตัวเอง FGU ≥10%) → ทางแก้คือ anchor ไปที่ S1 (KL/BC บนแรงผลักที่กู้ได้) หรือเทรน S2 จาก S1 แบบ freeze/residual
  - noise floor ต่ำ (≤5%) → env ของ S2 ทำให้ทักษะหาย ลองขยายช่วงกู้ได้เป็น U(0, 0.12) ให้ตรงกับ S1 (สมมติฐาน ค)

### รอบ 2026-10-09 02:45
- **job ที่จบ:** `20261009-021413-s1fgufloor` ใช้ 27:33 นาที (exit 0) noise floor ของ FGU (S1 update 125/150/175 เทียบกับ 200)
  FGU 7.1/2.4/11.9, 2.2/4.3/0.0, 0.0/4.3/10.9% (เฉลี่ย ~4.8%) รอดกลุ่มกู้ได้ 89.6–100% → noise มีจริงแต่ S2 (FGU 6.5–65%) ทำให้ทักษะหายจริง
- **วิเคราะห์ (ทำเอง):** `worklog/s2_per_impulse.py` แยกผลตามแรงผลัก ทักษะหายมากสุดที่ 0.08 (S2 21–88% เทียบ S1 75–96%) ส่วน 0.05 ยังดีกว่า
  ซึ่ง 0.08 เป็นขอบบนของช่วงกู้ได้ตอนเทรน S2 แต่ S1 เทรนด้วย U(0, 0.12) + U(0.13, 0.25) → สนับสนุนสมมติฐาน ค
- **Codex (ความเห็นที่สอง วิเคราะห์อย่างเดียว ไม่ได้แก้ไฟล์):** ไม่พบ bug ที่ทำให้ gate ตก แนะนำให้ (1) ลอง U(0, 0.12) ก่อน
  แล้ว (2) BC/KL anchor ไปที่ S1 บนแรงผลักที่กู้ได้ (ใช้ normalizer ของแต่ละ policy และไม่รวม state หลังล้ม)
  ไม่แนะนำให้ลด DAMAGE_W หรือเพิ่มจำนวน updates พบ bug ใน telemetry ที่ `train.py:153` ซึ่งนับ `falls` ต่อ step แทนต่อ episode (ยังไม่ได้แก้ เพราะไม่กระทบผล)
  log อยู่ที่ `auto-loop/.loop/codex/20261009-024544.log` บันทึกทั้งหมดลง Curriculum_Plan ส่วน 5 แล้ว
- **แก้ (ทำเอง):** เพิ่ม env `RECOVERABLE_MAX` (default 0.08 ผลเดิมไม่เปลี่ยน) ใน `run_stage2_pilot.sh`, `run_stage2_eval.sh` และ `run_stage2_eval_trend.sh`
  และเพิ่ม `scripts/run_stage2_wide.sh` (RECOVERABLE_MAX=0.12, DAMAGE_W=10000, lr 1e-4, เทรน + eval 200 + trend 50/100/150)
- **job ที่สั่ง:** `20261009-024529-s2wide` = `bash scripts/run_stage2_wide.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.12_hard0.5_posture1.0_s2_dmg10000/` (log ยืนยันแล้วว่า push<=0.12) คาดว่าใช้ ~2.5–3 ชม.
- **verify:** ไม่ได้รัน เพราะแก้แค่ shell script ไม่ได้แก้ src/tests และไม่อยากแย่ง CPU กับ job (`bash -n` ติด permission จึงไม่ได้ตรวจ syntax แต่ log แสดงว่าสคริปต์รันได้)
  ผลล่าสุด (02:43) คือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **งานถัดไป:** อ่าน s2_eval*.json ของ `push_0.12_..._s2_dmg10000` (รวมถึงผลแยกแรงผลักด้วย `worklog/s2_per_impulse.py`) แล้วบันทึกลง Curriculum_Plan ส่วน 5
  - ถ้าผ่าน gate ครบ 3 seeds ที่ update 200 → เขียน `auto-loop/milestones/m2_summary.json` แล้วแก้ตัวเลข S2 ใน M3 และเขียน m3_compute.json
  - ถ้าไม่ผ่าน → ทำ BC/KL anchor ไปที่ S1 (ส่งให้ Codex เขียนได้: เพิ่ม auxiliary loss ใน `train.py` ที่ใช้ S1 ตัวที่แช่แข็งไว้
    บน state ที่ยังไม่ล้มและเป็นแรงผลักที่กู้ได้ พร้อม test) ห้ามเลือก checkpoint ที่ผลดีเอง ต้องใช้ update 200 ทุก seed

### รอบ 2026-10-09 05:17
- **job ที่จบ:** `20261009-024529-s2wide` ใช้ 2:21 ชม. (exit 0) push กู้ได้ U(0, 0.12) (สมมติฐาน ค)
  update 200: รอดกลุ่มกู้ได้ 83.3 / 83.3 / 79.2% (S1 87.5 / 95.8 / 95.8%), FGU 16.7 / 15.2 / 19.6%,
  damage กลุ่มกู้ไม่ได้ 0.00086 / 0.00116 / 0.00042 (< S1 และ < ปล่อยตัว ทุก seed) → **M2 ไม่ผ่าน (ครั้งที่ 4)**
  trend FGU 0–56.5% ยังแกว่งอยู่ ทักษะยังหายที่ 0.08 บันทึกตาราง + ผลแยกตามแรงผลักลง Curriculum_Plan ส่วน 5 แล้ว
- **ทำอะไร:** ทางแก้ข้อ (2) ของ Codex คือ KL anchor ไปที่ S1 ตัวที่แช่แข็งไว้ **Codex เป็นคนเขียน** (prompt อยู่ที่ `worklog/codex_task_s2_anchor.md`)
  - `train.py`: `--anchor-coef/--anchor-checkpoint/--anchor-max-impulse`, `AnchorSamplesCallback` (เก็บ obs ที่แรงผลัก ≤ max และยังไม่ล้ม
    โดยดูจาก fallen ของ step ก่อน), แปลง obs กลับเป็นค่าดิบแล้ว normalize ด้วย obs_rms ของ S1, `anchor_step` (KL(S1‖θ) หลัง PPO update ทุกครั้ง
    5 epochs, batch 2048, ใช้ optimizer เดิม) และเพิ่มคอลัมน์ anchor_* ใน updates.csv เฉพาะตอนเปิด anchor
  - `run_stage1.sh`/`run_stage2_pilot.sh` รับ env ANCHOR (tag `_anc<ANCHOR>`) และสคริปต์ใหม่ `scripts/run_stage2_anchor.sh` (base recipe 0.08, dmg10000, ANCHOR=1.0)
  - `tests/test_anchor.py` (7 tests)
  - **ตรวจเอง:** อ่าน git diff แล้ว (ถ้า coef=0 พฤติกรรมเดิมไม่เปลี่ยน), smoke test 2 updates บน checkpoint S1 จริง (`worklog/smoke_anchor.sh`)
    ได้ ~9–11k samples ต่อ update และ KL ลดจาก 0.021 เหลือ 0.001–0.0016 ต่อ update
- **verify:** pytest ผ่าน (60 tests), M1 PASS, M2–M4 FAIL (ยังไม่มีผล)
- **job ที่สั่ง:** `20261009-051654-s2anchor` = `bash scripts/run_stage2_anchor.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0/` คาดว่าใช้ ~2.5–3 ชม. (anchor phase เพิ่มเวลาต่อ update เล็กน้อย)
- **งานถัดไป:** อ่าน s2_eval*.json ของ `s2_dmg10000_anc1.0` (+ `worklog/s2_per_impulse.py` และดู anchor_kl ใน updates.csv) แล้วบันทึกลง Curriculum_Plan ส่วน 5
  - ผ่านครบ 3 seeds ที่ update 200 → เขียน `auto-loop/milestones/m2_summary.json` แล้วแก้ตัวเลข S2 ในเอกสาร M3 และเขียน m3_compute.json
  - FGU ลดลงแต่ยังไม่ผ่าน → ลองเพิ่ม ANCHOR (เช่น 3.0) หรือ anchor + RECOVERABLE_MAX 0.12
  - ไม่ช่วยเลย → ถือว่าติดมาหลายรอบแล้ว ให้บันทึกหลักฐานและพิจารณาว่าเกณฑ์ FGU ≤10% เป็นไปได้หรือไม่ (noise floor ~4.8%, สูงสุด 11.9%)

### รอบ 2026-10-09 07:47
- **job ที่จบ:** `20261009-051654-s2anchor` ใช้ 2:29 ชม. (exit 0) KL anchor ไปที่ S1 (ANCHOR=1.0, 5 epochs)
  update 200: รอดกลุ่มกู้ได้ 95.8 / 93.8 / 91.7% (S1 87.5 / 95.8 / 95.8%), FGU 0.0 / 2.2 / 8.7% → ผ่านเกณฑ์รอดและ FGU ทุก seed (ครั้งแรก)
  แต่ damage กลุ่มกู้ไม่ได้ 0.00176 / 0.00164 / 0.00153 (S1 0.00187 / 0.00190 / 0.00143, ปล่อยตัว 0.00161) → 63001/63002 > ปล่อยตัว, 63003 > S1
  → **M2 ไม่ผ่าน (ครั้งที่ 5) ตอนนี้ติดที่เกณฑ์ damage** trend: FGU ≤13% ทุก checkpoint แต่ damage ไม่ลดเลย บันทึกตารางลง Curriculum_Plan ส่วน 5 แล้ว
- **วิเคราะห์ (ทำเอง):** `worklog/anchor_kl.py` พบว่า PPO ดัน KL ไป ~0.025 แล้ว anchor ดึงกลับเหลือ ~0.002–0.003 ทุก update (anchor แรงเกินไป)
  anchor เป็น phase แยกที่ใช้ Adam ซึ่งไม่ขึ้นกับ scale ของ loss จึงลด coef แทบไม่มีผล ตัวคุมความแรงจริงคือจำนวน epoch
- **แก้ (ทำเอง):** `train.py` เพิ่ม `--anchor-epochs` (ค่าเริ่มต้น = n_epochs 5 ผลเดิมไม่เปลี่ยน, บันทึกลง manifest),
  env `ANCHOR_EPOCHS` ใน `run_stage1.sh`/`run_stage2_pilot.sh`/`run_stage2_anchor.sh` (tag `_ae<N>`), และเพิ่ม assert ใน `tests/test_anchor.py`
- **verify:** pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **job ที่สั่ง:** `20261009-074927-s2anc_ae1` = `ANCHOR_EPOCHS=1 bash scripts/run_stage2_anchor.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0_ae1/` คาดว่าใช้ ~2.5 ชม.
- **งานถัดไป:** อ่าน s2_eval*.json ของ `anc1.0_ae1` (+ `worklog/anchor_kl.py s2_dmg10000_anc1.0_ae1` ตรวจว่า manifest มี anchor_epochs=1)
  - ผ่านครบ 3 seeds ที่ update 200 → เขียน `auto-loop/milestones/m2_summary.json` แล้วแก้ตัวเลข S2 ในเอกสาร M3 + เขียน m3_compute.json
  - FGU ดีแต่ damage ยังไม่ลด → ลอง anchor + RECOVERABLE_MAX 0.12 (wide ลด damage ได้มากที่สุด) หรือ anchor ที่ใช้เฉพาะ state ก่อนผลัก/ไม่กี่ step หลังผลัก
  - FGU กลับมาสูง → ลอง ANCHOR_EPOCHS=2
  - ติดมาหลายรอบแล้ว (5 รอบ) ถ้ายังไม่ผ่าน ให้ขอความเห็นที่สองจาก Codex อีกครั้ง (วิเคราะห์อย่างเดียว) เรื่อง trade-off FGU กับ damage

### รอบ 2026-10-09 10:55
- **job ที่จบ:** `20261009-074927-s2anc_ae1` ใช้ 3:04 ชม. (exit 0) anchor ANCHOR_EPOCHS=1 (manifest anchor_epochs=1 ✓)
  update 200: รอดกลุ่มกู้ได้ 87.5 / 95.8 / 91.7% (S1 87.5 / 95.8 / 95.8), FGU 7.1 / 2.2 / 8.7%, damage กลุ่มกู้ไม่ได้ 0.00133 / 0.00175 / 0.00125
  (S1 0.00187 / 0.00190 / 0.00143, ปล่อยตัว 0.00161) → 63001 และ 63003 ผ่านทุกเกณฑ์ ส่วน **63002 damage > ปล่อยตัว** → **M2 ไม่ผ่าน (ครั้งที่ 6) แต่ผ่าน 2/3 ซึ่งใกล้ที่สุดแล้ว**
  63002 มี damage 0.0017–0.0018 ทุก checkpoint ส่วน anchor_kl หลัง anchor ~0.010–0.020 (ae5 ได้ ~0.002) บันทึกตาราง + ผลแยกตามแรงผลักลง Curriculum_Plan ส่วน 5 แล้ว
- **ทำอะไร (ทำเอง):** ให้ `scripts/run_stage2_anchor.sh` รับ env `RECOVERABLE_MAX` (default 0.08 ผลเดิมไม่เปลี่ยน) เพื่อรวม anchor ae1 กับ wide U(0, 0.12)
  เพราะ wide ลด damage ได้มากที่สุด (63002 ได้ 0.00116) ส่วน anchor ลด FGU ได้ (anchor ใช้ช่วง ≤0.12 ด้วย เพราะ anchor_max_impulse = max_push_impulse)
- **Codex (ความเห็นที่สอง วิเคราะห์อย่างเดียว ไม่ได้แก้ไฟล์):** prompt อยู่ที่ `worklog/codex_task_s2_damage_analysis.md` และ log อยู่ที่ `auto-loop/.loop/codex/20261009-105715.log`
  สรุปว่าไม่มี state จาก hard push หลุดเข้า anchor และพบ bug ที่ obs_rms อัปเดตไปแล้วก่อน callback แปลง obs กลับ (`train.py:207`)
  ตรวจเองแล้วว่าผลแทบเป็นศูนย์ (obs_rms ของ S1 มี count ~3.3M) ทางแก้ที่จัดลำดับไว้: แก้ raw obs → KL อยู่ใน PPO objective → anchor เฉพาะช่วงก่อนผลัก + K step แรก
- **verify:** ไม่ได้รัน เพราะแก้แค่ shell script (เพิ่ม default env) ไม่แตะ src/tests และไม่อยากแย่ง CPU กับ job ผลล่าสุด (10:55) คือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **job ที่สั่ง:** `20261009-105614-s2anc_wide` = `RECOVERABLE_MAX=0.12 ANCHOR_EPOCHS=1 bash scripts/run_stage2_anchor.sh 63001 63002 63003`
  ผลออกที่ `results/stage2/seed_*/push_0.12_hard0.5_posture1.0_s2_dmg10000_anc1.0_ae1/` คาดว่าใช้ ~3 ชม.
  (หมายเหตุ: `worklog/anchor_kl.py` ต้องรันด้วย path `/mnt/c/RL_Fall/worklog/...` เพราะ worklog ไม่ถูก copy ไป WSL และ glob ของมันจับ run push_0.12 ด้วย)
- **งานถัดไป:** อ่าน s2_eval*.json ของ `push_0.12_..._anc1.0_ae1` (+ `s2_per_impulse.py`, `anchor_kl.py`) แล้วบันทึกลง Curriculum_Plan ส่วน 5
  - ผ่านครบ 3 seeds ที่ update 200 → เขียน `auto-loop/milestones/m2_summary.json` (ชี้ไปที่ run นี้ทั้ง 3 seeds) แล้วแก้ตัวเลข S2 ใน M3 + เขียน m3_compute.json
  - ไม่ผ่าน → ทำตามลำดับของ Codex: ย้าย KL เข้าไปใน PPO loss (ส่งให้ Codex เขียนพร้อม test และแก้ raw obs capture ไปด้วย)
    หรือ anchor เฉพาะช่วงก่อนผลัก + K step แรก ห้ามเลือก checkpoint ที่ผลดีเอง ต้องใช้ update 200 ทุก seed

### รอบ 2026-10-09 12:40
- **ตัวนำ:** Claude (ตัวช่วย: Codex)
- **job ที่จบ:** ไม่มี `20261009-105614-s2anc_wide` ยังรันอยู่ (1:42 ชม. ตอนเริ่มรอบ, 63001/63002 เทรนเสร็จแล้ว กำลังเทรน 63003 แล้วจะต่อด้วย eval + trend) คาดว่าเหลืออีก ~1.3 ชม.
- **ทำอะไร (Claude ทำเอง):** งาน M3 ระหว่างรอ แก้ `scripts/lanta/s2_pilot.sbatch` ให้สร้าง TAG ตามกฎเดียวกับ `run_stage2_pilot.sh` (เพิ่ม `_anc<ANCHOR>`/`_ae<ANCHOR_EPOCHS>`)
  เพื่อให้รัน recipe ที่มี anchor บน LANTA ได้ และ eval หา run ที่เทรนไว้เจอ (RECOVERABLE_MAX ส่งต่อทาง env) และเพิ่มหมายเหตุในส่วน 6 ของ `planning/LANTA_Compute_Estimate_TH.md`
  ตรวจด้วย `bash -n` ผ่านแล้ว **Codex รีวิว diff แล้วตอบ OK** (TAG ตรงกันทั้ง default และ anc1.0_ae1 + 0.12 และใช้กับ set -u ได้) log อยู่ที่ `auto-loop/.loop/codex/20261009-123912.log`
- **verify:** ไม่ได้รัน เพราะแก้แค่ sbatch/เอกสาร ไม่แตะ src/tests และไม่อยากแย่ง CPU กับ job ผลล่าสุด (12:37) คือ pytest ผ่าน, M1 PASS, M2–M4 FAIL
- **job ที่สั่ง:** ไม่มี (สร้าง `auto-loop/WAIT_FOR_JOBS` ไว้แล้ว)
- **งานถัดไป:** เหมือนรอบ 10:55 คืออ่าน s2_eval*.json ของ `push_0.12_..._anc1.0_ae1` (+ `s2_per_impulse.py`, `anchor_kl.py`) แล้วบันทึกลง Curriculum_Plan ส่วน 5 พร้อมเวลา job
  - ผ่านครบ 3 seeds ที่ update 200 → เขียน m2_summary.json แล้วแก้ข้อ 2–5 ของ LANTA_Compute_Estimate (S2 = 200 updates = 3.3M) + เขียน m3_compute.json (ใส่ sbatch ทั้ง 3 ไฟล์)
  - ไม่ผ่าน → ย้าย KL เข้าไปใน PPO loss + แก้ raw obs capture (`train.py:207`) ตามลำดับที่ Codex เสนอ

### รอบ 2026-10-09 14:45
- **ตัวนำ:** Codex; ตัวช่วย Claude ใช้เฉพาะความเห็นที่สองและรีวิว (วิเคราะห์อย่างเดียว ไม่มีการแก้ไฟล์)
- **งานที่เลือก (M2, Codex ทำเอง):** ทดลองเปลี่ยนจาก KL phase แยกหลัง PPO เป็น KL ใน objective เดียวกัน เพราะ M2 ติด trade-off กู้/เสียหายมา 7 recipes
  เพิ่ม `src/rl_fall/anchor_ppo.py` (อ้างอิง PPO.train ของ SB3 2.9.0 ที่ pin อยู่ใน pyproject พร้อม MIT notice), CLI `--anchor-mode objective`
  เก็บโหมด `post_update` เดิมเพื่อทำซ้ำผลเก่า; coefficient=1.0 มีน้ำหนักเทียบ PPO ก่อน Adam rescale gradient
  สุ่ม uniform with replacement จาก state กู้ได้ที่ยังไม่ล้มแยกจาก PPO minibatch; frozen S1/normalizer ไม่อัปเดต
  โหมดใหม่เก็บ raw observation ก่อน action จริง จึงไม่แปลงย้อนด้วย RMS ที่ถูกอัปเดตหลัง step และไม่สูญข้อมูลจาก clipping
  ไม่คิด KL ตอน critic warmup; teacher/rollout samples ไม่ถูกใส่ใน checkpoint และโหลดต่อจาก S1/ตัวเองหรือประเมินด้วย PPO.load ได้
  log KL ใน objective, PPO policy loss, gradient norm ก่อน clip, full epochs, optimizer steps และ early stop; manifest ระบุ RNG/sampling/weighting
  ส่ง env/CLI/tag ใน run_stage1/run_stage2_pilot และ LANTA sbatch ให้ตรงกัน (ไม่ submit); pilot หยุดเมื่อ seed แรกเกิด error
  เพิ่ม `scripts/run_stage2_objective.sh` ล็อก train/eval update=200, trend 50/100/150 เป็น diagnostic เท่านั้น
- **job ที่จบ:** `20261009-105614-s2anc_wide` ใช้ **3:31:55 ชม.**, exit 0; ตรวจ manifest ทั้ง 3 seeds (recoverable max=.12, anchor_epochs=1)
  update 200: รอดกู้ได้ 83.3 / 95.8 / 83.3% (S1 87.5 / 95.8 / 95.8%), FGU 11.9 / 4.3 / 17.4%
  damage กู้ไม่ได้ 0.001461 / 0.001629 / 0.001391 (S1 0.001867 / 0.001899 / 0.001427, ปล่อยตัว 0.001607 ทุก seed), head share 0% ทุก seed
  63001 ไม่ผ่าน FGU; 63002 damage สูงกว่าปล่อยตัว 1.4%; 63003 ไม่ผ่านรอดและ FGU → **M2 ยังไม่ผ่าน ครั้งที่ 7 ไม่มี seed ผ่านครบที่ update 200**
  บันทึกผลครบทั้ง final/trend และเวลาใน `planning/Curriculum_Plan_TH.md` ส่วน 5; ไม่เลือก checkpoint ก่อนหน้าและไม่เขียน m2_summary.json
- **ตรวจทางซอฟต์แวร์:** เพิ่ม 4 tests (raw obs/RMS/clipping/reset+hard mask, KL gradient/teacher/critic, empty anchor เหมือน upstream+save/load, joint training/warmup/resume)
  พิสูจน์ regression raw obs แบบ red/green: override ใน process ชั่วคราวให้ใช้ callback เดิมแล้ว test ล้ม (12/12 ค่าไม่ตรง), โค้ดใหม่ผ่าน
  real-body smoke 8 envs, 2 updates seed 63001 จบ 37.7 วินาที (steady 28.9s, 1135 t/s ขณะ verify รันพร้อมกัน ไม่ใช้เป็น throughput M3)
  run: `results/stage2_objective_smoke/3d_A_env8_subproc_cpu_seed63001_t4_20261009T143930`; samples 8861/11438, KL ก่อน→หลัง .000015→.012294 / .012284→.019039
  smoke เป็นการตรวจการรัน ไม่มี survival/damage eval และไม่ใช่หลักฐานผ่าน gate
- **Claude ความเห็นที่สอง/รีวิว:** prompt `tmp/claude_s2_objective_analysis.md` และ `tmp/claude_s2_objective_review.md`; report `auto-loop/reports/claude-helper.md`
  raw logs `auto-loop/.loop/claude/20261009-143113.jsonl` (486s) และ `20261009-144105.jsonl` (105s); ไม่พบ blocker และไม่ได้แก้ไฟล์ ตรวจ git diff เองแล้ว
  ใช้ข้อเสนอ diagnostics/ล็อก update200; ไม่ใช้ข้อเสนอเปลี่ยน FGU ให้เท่า S1 เพราะขัดเกณฑ์เดิมของผู้ใช้
  KL_before ใน objective วัดก่อน PPO แต่ legacy วัดหลัง PPO/ก่อน anchor จึงห้ามเปรียบเทียบค่านี้ข้ามโหมดตรงๆ
  การ resume ไม่ใช่ bit-identical เพราะไม่ได้กู้ RNG state (ข้อจำกัดเดิม); objective สุ่ม anchor ใช้ torch RNG จึงไม่อ้าง trajectory matched กับ legacy
- **verify:** รัน `pwsh -NoProfile -File auto-loop/verify.ps1` หลังแก้โค้ด/diagnostics ล่าสุด **pytest ผ่าน 64 tests**, tests exit=0, M1 PASS, M2–M4 FAIL (goal exit=1)
  goal-status เวลา 2026-10-09 14:42:40; `.loop/last-verify.txt` ยังเป็นผลก่อนรอบ (ลูปเป็นผู้เขียนไฟล์นี้)
  `bash -n` สคริปต์ที่แก้และ `git diff --check` ผ่าน รวมหลังล็อก UPDATES/UPDATE=200; ไม่มี commit/push/merge และไม่แตะไฟล์ควบคุมลูปที่ห้ามแก้
- **ปัญหา:** เทสต์เปรียบเทียบ RNG ล้มครั้งแรกเพราะรีเซ็ต seed แทนคืน RNG หลังสร้าง learner แก้ fixture แล้วผ่าน (ไม่ใช่บั๊ก product)
  helper ครั้งแรกค้น package ด้วย find / แล้วค้าง ~5 นาที จึงหยุดเฉพาะ process find PID 675 และใช้ literal installed package path; ไม่กระทบ job เทรน
  ยังไม่มีหลักฐานว่า objective mode ผ่าน M2; ใช้ coefficient=1.0 และ recoverable=.08 เป็นการทดลองเดียวที่กำหนดก่อนรัน ไม่เปลี่ยน reward/damage/gate
- **job ที่สั่ง:** `20261009-144418-s2joint` = `ANCHOR=1.0 RECOVERABLE_MAX=0.08 bash scripts/run_stage2_objective.sh 63001 63002 63003`
  เทรนทีละ seed ใน job เดียว, update 200 ทุก seed, final eval แล้ว trend; คาดว่า **3.5–4 ชม.**
  ผลที่ `results/stage2/seed_*/push_0.08_hard0.5_posture1.0_s2_dmg10000_anc1.0_objective/3d_*/s2_eval*.json`
- **งานถัดไป:** สร้าง `auto-loop/WAIT_FOR_JOBS` แล้วจบรอบ ให้รอบถัดไปอ่าน final/trend ทั้ง 3 seeds และ jobs.md บันทึกเวลา/ตัวเลขใน Curriculum_Plan
  ตรวจ manifest anchor_mode=objective, raw_obs=true, coef=1.0, max_impulse=.08, measured_updates=200, explicit S1 checkpoint; ดู KL/epochs/optimizer_steps/gradnorm/early_stop จาก updates.csv
  ผ่านครบตามเกณฑ์ GOAL.md ที่ final200 ทุก seed → เขียน m2_summary.json ชี้ run นี้ทั้ง 3 seeds แล้วทำ M3; ไม่ผ่าน → ให้ Claude วิเคราะห์ diagnostics เทียบ ae1/wide ก่อนเลือกการทดลองใหม่
  ห้ามหยิบ trend checkpoint ที่ดีมาแทน และยังไม่เขียน transitions S2 to gate/M3 milestone ก่อนมีผลผ่านจริง

### รอบ 2026-10-09 19:23
- **ตัวนำ:** Codex; ตัวช่วย Claude ให้ความเห็นที่สองและรีวิวสั้น วิเคราะห์อย่างเดียว ไม่มีการแก้ไฟล์
- **งานที่เลือก (M2, Codex ทำเอง):** ประเมินความแปรปรวนและรูปแบบการรับแรงของ objective coefficient=1 ที่ final200
  ก่อนเลือกการเทรนถัดไป; ใช้ systematic-debugging, doc-coauthoring และ verification-before-completion
  ปรับ workflow เอกสารเป็นอ่าน/เขียน/รีวิวอัตโนมัติตามคำสั่งไม่มีมนุษย์ ไม่ถามหรือรอคำยืนยัน
- **job ที่จบ:** `20261009-144418-s2joint` ใช้ **4:23:26 ชม.**, exit 0 (jobs.md ตรงกับ job metadata 15806 วินาที)
  ตรวจ manifest ทั้ง 3 seeds: objective/raw_obs=true/coef1/max=.08/update200/initial+teacher M1 ของ seed เดียวกัน
  final200: รอดกลุ่มกู้ได้ S2 87.5 / 95.8 / 93.8% เทียบ S1 87.5 / 95.8 / 95.8%, FGU 7.1 / 4.3 / 6.5%
  damage กู้ไม่ได้ S2 0.001088945 / 0.001682237 / 0.001292352; S1 0.001866519 / 0.001899228 / 0.001426663,
  ปล่อยตัว 0.001606949 ทุก seed; head share 0.00813 / 0 / 0.00854% → **M2 ยังไม่ผ่านครั้งที่ 8, ผ่านครบ 2/3**
  63002 damage สูงกว่าปล่อยตัว 4.69%, ส่วนลำตัวถ่วงน้ำหนัก 93.65%; มีผู้รอด hard 3/48 (S1 0), mean รวมผู้รอดตามนิยามเดิม
  update150 ผ่านครบทั้ง 3 seeds แต่เป็น trend ที่กำหนดก่อนรัน ห้ามใช้แทน endpoint200; ไม่เขียน milestone M2/M3
  บันทึก final/trend/per-impulse/ส่วนร่างกาย/diagnostics/เวลาใน Curriculum_Plan ส่วน5 และ `auto-loop/reports/s2joint_diagnostics_20261009.txt`
  KL_after เฉลี่ย update151–200=.03329/.03342/.03159, ทุก update หลัง50 มี5 epochs/40 optimizer steps,
  earlystopรวม2/1/0 จึงไม่มีหลักฐานว่า target_kl หยุดก่อนเวลาทำให้ตก gate; throughput WSL 984.65/834.77/1114.05 t/s (ไม่ใช่ LANTA)
- **Claude ความเห็นที่สอง/รีวิว:** เรียกผ่าน tools/claude.ps1 ด้วย `tmp/claude_joint_second_opinion.md` (64s)
  และ `tmp/claude_joint_diagnostic_review.md` (67s); logs `auto-loop/.loop/claude/20261009-191132.jsonl` / `20261009-191853.jsonl`
  report `auto-loop/reports/claude-helper.md`; ตรวจ git diff ทุกครั้งและอ่านไฟล์ใหม่เอง ไม่มี helper แก้ src/tests/docs
  ยืนยัน gate interpretation; เห็นว่า coef.5 เป็นการเปลี่ยนตัวเดียวแต่หลักฐานตอบสนองต่อความแรง anchor ของ63002ยังไม่ชัด
  จึงรับคำแนะนำให้ frozen-policy eval ชุดใหม่ใหญ่ขึ้นก่อน ไม่สั่งเทรน coefficient.5 และไม่อ้างว่า checkpoint swing เป็น evaluation SE
- **สิ่งที่เพิ่ม:** `scripts/stage2_diagnostics.py` ใช้ run_episode/env/summarize ของ stage2_eval เดิมโดยไม่แก้ evaluator/gate
  เก็บทุก episode, per-part weighted damage, falls-only/survivors-only means, paired deltas ต่อ S1/passive,
  SE + bootstrapCI95 บน reset-seed/angle clusters ที่ reuseข้ามimpulse; descriptive torso-tail, source/evidence hashes
  `scripts/run_stage2_objective_diagnostic.sh` ล็อก paths/timestamps S2ทั้ง3ตามrunจริง กับ S1 final200, ไม่มี latest-run selection
  fixed reset-base19000/scale4 → 192 easy+192 hard ต่อpolicyต่อseed รวม3456episodes; diagnostic_only=true/milestone_eligible=false
  CI12ชุดเป็น exploratory ไม่ปรับmultiple-comparison; seedและangleถูกresampleร่วมกัน ไม่ใช่ CI ที่ตรึง angle gridจริง
  ยังไม่รู้ power ตรวจ excess ~.000075; CIคร่อมศูนย์ไม่แปลว่าเท่ากัน; per-fall subsets ไม่ใช่ paired causal comparison
- **ตรวจทางซอฟต์แวร์:** เพิ่ม4 testsพิสูจน์ pairing/clusterSEไม่ถือimpulsesที่reuse seedเป็นอิสระ/denominators/invalid pairs/new seed design
  real-policy smoke63001 base29000 scale.04 มี15records (ไม่ใช่ผลผ่านgate), flags/hashes/countsตรงและreuseไม่เขียนทับผ่าน
  run `results/stage2_diagnostics/smoke_joint_seedbase29000_scale004/seed_63001`; evidence `auto-loop/reports/s2diag_smoke_check_20261009.txt`
  archive hashของ S1finalกับupdate200ต่างกัน ทำให้ checkสมมติฐาน byte-identical ล้มครั้งแรก; ตรวจต้นเหตุในลำดับsaveแล้ว
  ใช้ PPO.load ตรวจ policy tensorsทุกตัว + obs_rms mean/var/count, clip_obs/epsilon ตรงกันครบ3seeds จึงไม่มี teacher/baseline mismatch
- **verify:** หลังเพิ่มโค้ดรัน `pwsh -NoProfile -File auto-loop/verify.ps1`: **68 testsผ่าน**, tests exit=0,
  M1 PASS, M2–M4 FAIL (goal exit=1), goal-status2026-10-09 19:20:21; bash -n/compileall/git diff --check ผ่าน
  ไม่มีการแก้ไฟล์ควบคุมลูปที่ห้ามแก้, ไม่มีcommit/push/merge/submitLANTA, ไม่แก้หรือลบผลเดิม
- **job ที่สั่ง:** `20261009-192213-s2joint_diag` = `bash scripts/run_stage2_objective_diagnostic.sh`
  ผ่าน wsl-job.ps1, คาด **45–60 นาที** (3seedsต่อกัน, evalเท่านั้น ไม่มีเทรน); ตรวจ jobs.ps1 เป็นrunning และ Python PID704ใช้pathsถูกต้อง
  output `results/stage2_diagnostics/joint_coef1_seedbase19000_scale4/seed_*/episodes.json` กับ `diagnostic.json`
- **ปัญหา:** M2ยังตกเกณฑ์damage63002; ไม่มีหลักฐานว่าเป็นไปไม่ได้ทางฟิสิกส์ จึงไม่สร้างSTOPและไม่ลดเกณฑ์
- **งานถัดไป:** สร้าง `auto-loop/WAIT_FOR_JOBS` แล้วจบรอบ; รอบถัดไปอ่าน diagnostic.json/episodes.json ครบ3seeds + jobs.md
  บันทึกเวลาและ paired means/SE/CI/torso distribution/falls-only ใน Curriculum_Plan; ตรวจ provenance final200/base19000/scale4/sourcehash
  **ผล diagnostic ชุดใหม่ใช้วิเคราะห์เท่านั้น แม้ผ่านตัวเลขก็ไม่เปลี่ยน verdict M2เดิม ไม่ใช้เขียนm2_summary.json**
  เลือกการทดลองใหม่หนึ่งชิ้นจากขนาดpaired excessต่อSEและตำแหน่งรับแรง: หากชัดและมาจากtorsoพิจารณา time-window anchorหรือshaping
  ถ้าCIคร่อมศูนย์ให้รายงานไม่แน่นอนและเลือกการทดลองที่คาดเปลี่ยนพฤติกรรมชัดเจน ไม่ไล่ค่าcoefเพื่อให้scenarioเดิมผ่านโดยบังเอิญ
  ต้องกำหนด recipe/endpoint/update200/3seeds ก่อนเทรนครั้งใหม่ ไม่หยิบcheckpoint150ที่ผ่านมาแทน; M3ยังรอtransitions S2ถึงgateจริง
