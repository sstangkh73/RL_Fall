# ประเมิน compute สำหรับ LANTA (M3) — ฉบับร่าง

สถานะ 8 ต.ค. 2026: **ร่าง** ตัวเลข S1 มาจากผลจริง ส่วน S2 ยังไม่ผ่าน gate (M2)
ตัวเลข S2 จึงเป็นค่าสมมติ และต้องแก้เมื่อรู้ว่าต้องใช้กี่ updates ถึงผ่าน gate
ยังไม่เขียน `auto-loop/milestones/m3_compute.json` จนกว่าจะรู้ค่านั้น

สูตรตามแผนข้อ 7: node-hours = Σ (transitions ต่อ run × จำนวน run) ÷ throughput ต่อ node × 1.3 (buffer)

## 1. Throughput ที่วัดได้ (WSL2, i5-14400F 16 threads)

ทุก run ใช้ 8 envs + learner 4 threads และ 16,384 transitions ต่อ update
ค่ามาจาก `steady_transitions_per_second` ใน `manifest.json` ของแต่ละ run

| run | seed 63001 | 63002 | 63003 |
|---|---|---|---|
| S1 R2 v4 (`natural4_r2`, รันเดี่ยว) | 1,931 | 1,945 | 1,948 |
| S2 (`s2_dmg10000`, รันเดี่ยว) | 1,751 | 1,774 | 1,777 |
| S1 R1 v3 (รัน 2 job พร้อมกัน) | 1,526* | 481 | 481 |

\* ช่วงที่ 63001 รันเดี่ยวหลังอีก job จบ
ถ้ารันพร้อมกันเกินจำนวน core จะช้าลงหลายเท่า (481 เทียบกับ ~1,930) จึงต้องไม่ให้ thread รวมเกินจำนวน core ของ node

## 2. Transitions ถึง gate

| ขั้น | updates ต่อ seed | transitions ต่อ seed | ที่มา |
|---|---|---|---|
| S1 (A 200 + B 300 + CP 150 + R1 200 + R2 200) | 1,050 | 17.2M | `scripts/run_stage1_v1_recipe.sh` ผ่าน M1 ทั้ง 3 seeds |
| S2 | **ยังไม่รู้** (pilot ใช้ 200 updates = 3.3M แต่ยังไม่ผ่าน gate) | สมมติ 6.6M (400 updates) | ต้องแก้หลัง M2 |
| S3 | ยังไม่ได้เริ่ม | สมมติ 13.1M (800 updates) | งานใหม่ จึงสมมติว่าใช้ 2 เท่าของ S2 |

ต้นทุนช่วงพัฒนาของ S1 จริง: R1/R2 ต้องเทรนซ้ำ 3 รอบ (v2, v3, v4) จึงใช้ ~1,850 updates ต่อ seed หรือ ~1.8 เท่าของ recipe สุดท้าย

## 3. จำนวน run ของงานเต็ม (สมมติ)

| ส่วน | config | seeds | transitions ต่อ run | รวม |
|---|---|---|---|---|
| S1 recipe (ทำซ้ำบน LANTA) | 1 | 5 | 17.2M | 86M |
| S2 พัฒนา + ผลหลัก (DAMAGE_W, เส้นแบ่งแรงผลัก, LR) | 8 | 3 | 6.6M | 157M |
| S3 หลัก + controls 3 แบบ + λ sweep 5 ค่า | 9 | 3 | 13.1M | 354M |
| S3 ต้นทุนช่วงพัฒนา (×2 ตามประสบการณ์ S1) | | | | +354M |
| eval (survival, s2_eval, counterfactual) ~10% | | | | +95M |
| **รวม** | | **56 runs** (ไม่นับช่วงพัฒนา) | | **~1,046M** |

## 4. Throughput ต่อ node ของ LANTA (สมมติ ต้องวัด)

- LANTA CPU node: AMD EPYC 7713 64C 2.0 GHz ([TOP500](https://top500.org/system/180125)) ตัวอย่าง batch script ของ ThaiSC
  ขอ `-c 128` ต่อ node และมี partition compute/memory/gpu ([ThaiSC docs](https://thaisc.atlassian.net/wiki/x/BYDSEQ))
  ข้อมูลระบบเพิ่มเติม: [AMD case study](https://www.amd.com/en/resources/case-studies/nstda.html)
  ส่วนที่ว่า 1 node มี 2 socket = 128 cores อนุมานจากตัวอย่าง `-c 128`
- แต่ละ run ใช้ ~12 threads จึงวางได้ **10 runs ต่อ node** (120 threads) ลดจาก 12 ในแผนข้อ 7 เพราะเห็นแล้วว่าถ้า thread เกินจะช้าลงมาก
- ต่อ core ของ EPYC 7713 (boost 3.675 GHz) น่าจะช้ากว่า i5-14400F (P-core boost 4.7 GHz) จึงสมมติ ~1,200 t/s ต่อ run (~0.62 เท่า)
- throughput ต่อ node ≈ 10 × 1,200 = **12,000 t/s** ≈ 43M transitions ต่อ node-hour
- **ต้องวัดจริง** ด้วย `scripts/lanta/bench_throughput.sbatch` (K=10, 20 updates, ใช้ ~1 node-hour) ก่อนขอโควตาใหญ่

## 5. Node-hours

1,046M ÷ 12,000 t/s = 87,200 s = 24.2 node-hours × 1.3 = **~31 node-hours** (~4,000 core-hours)

ความไม่แน่นอนหลัก:
- S2/S3 อาจต้องใช้ updates มากกว่าที่สมมติหลายเท่า (S2 ยังไม่ผ่าน gate ใน 200 updates)
- ถ้าวัดแล้วได้ throughput ต่อ node ต่ำกว่าที่สมมติ 2 เท่า จะได้ ~62 node-hours
- จึงเสนอให้ขอ **~100 node-hours** ในรอบแรก (เผื่อไว้ ~3 เท่า) แล้วค่อยขอเพิ่มหลังได้ตัวเลข S3

ข้อสังเกต: งานนี้เล็กเมื่อเทียบกับขนาด LANTA เหตุผลหลักที่ต้องใช้ LANTA คือ**รันหลาย seed และหลาย config พร้อมกัน**
(เครื่องนี้รันได้ทีละ run ถ้าซ้อนกันจะช้าลงมาก) ไม่ได้มาจาก run เดี่ยวที่ใหญ่
56 runs บนเครื่องนี้ใช้ ~150 ชั่วโมงถ้ารันต่อกัน ส่วนบน LANTA run แต่ละชุดที่วางพร้อมกันบน 6 nodes จบใน ~3–4 ชั่วโมง

## 6. Slurm scripts (ยังไม่ได้ submit)

| ไฟล์ | งาน |
|---|---|
| `scripts/lanta/bench_throughput.sbatch` | วัด throughput ต่อ node (K runs พร้อมกัน) แล้วพิมพ์ผลรวม |
| `scripts/lanta/s1_recipe.sbatch` | S1 recipe ครบทุกขั้น หลาย seed พร้อมกันบน 1 node (resubmit แล้ว resume ได้) |
| `scripts/lanta/s2_pilot.sbatch` | S2 fine-tune + `s2_eval` หลาย seed พร้อมกัน |

ก่อนรันต้องแก้ `-A <project-account>` ติดตั้ง venv ที่ `~/venvs/rl_fall` (หรือส่ง `PY=`) และตรวจชื่อ partition กับ time limit ของ LANTA ปัจจุบัน

## สิ่งที่ต้องทำเพื่อปิด M3

1. M2 ผ่าน gate → แทนค่า S2 ในข้อ 2 ด้วย updates ที่ใช้จริง และคิดข้อ 3–5 ใหม่
2. เขียน `auto-loop/milestones/m3_compute.json` (node_hours, transitions_to_gate, throughput_per_node, runs, sbatch)
