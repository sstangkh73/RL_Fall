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
