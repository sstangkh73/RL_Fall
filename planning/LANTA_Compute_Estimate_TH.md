# ประเมิน compute สำหรับ LANTA (M3)

สถานะ 10 ต.ค. 2026: M1 และ M2 ผ่าน gate ครบ 3 seeds แล้ว ตัวเลข transitions ของ S1/S2 ด้านล่างมาจาก run ที่ใช้เป็นหลักฐานจริง ส่วน S3 ยังเป็นแผน จึงระบุเป็นสมมติฐานวางแผน ไม่ใช่ผลทดลอง

## 1. ข้อมูลที่วัดได้จาก run ที่ผ่าน gate

ทุก run ใช้ 8 envs, 2,048 steps/env/update = 16,384 transitions/update และ learner 4 threads

| ขั้น/recipe | updates ต่อ seed | transitions ต่อ seed | throughput WSL ต่อ seed (t/s) |
|---|---:|---:|---:|
| S1 `natural4_r2` | 1,050 รวม A+B+CP+R1+R2 | 17,203,200 | 1,931 / 1,945 / 1,948 |
| S2 `hardnobonus` | 200 | 3,276,800 | 1,229 / 1,243 / 1,180 |

throughput ในตารางเป็นค่า `steady_transitions_per_second` จาก manifest ของ endpoint R2/S2 ของแต่ละ seed
ไม่ใช่ค่าเฉลี่ยของทุกช่วง update ใน recipe ทั้งหมด

S1 คิดจาก A=200, B=300, CP=150, R1=200, R2=200 updates ต่อ seed ตาม recipe จริง
(`scripts/run_stage1_v1_recipe.sh`). S2 คิดจาก final200 ของ
`scripts/run_stage2_hardnobonus.sh`; การประเมิน 192+192 episodes ไม่ถูกรวมเป็น training transitions
และเผื่อเป็น evaluation overhead แยก 10% ในการคำนวณรวม

## 2. Transitions ถึง gate

| ขั้น | ที่มาของตัวเลข | transitions ต่อ run/seed |
|---|---|---:|
| S1 | endpoint `natural4_r2`, 1,050 updates | 17,203,200 |
| S2 | endpoint `hardnobonus`, 200 updates | 3,276,800 |
| S3 | สมมติฐานวางแผนเบื้องต้น 800 updates; ยังไม่เริ่ม | 13,107,200 |

ค่า S3 เป็นสมมติฐานสำหรับขอ compute เท่านั้น ต้องแทนด้วย transitions ถึง gate จริงเมื่อเริ่ม S3
และห้ามใช้เป็นหลักฐานว่า S3 เรียนรู้แล้ว

## 3. ขอบเขตงานเต็มสำหรับประมาณการ

| ส่วน | config | seeds | transitions ต่อ run | รวม transitions |
|---|---:|---:|---:|---:|
| S1 ทำซ้ำเพื่อยืนยัน | 1 | 5 | 17,203,200 | 86,016,000 |
| S2 ablation/threshold/LR | 8 | 3 | 3,276,800 | 78,643,200 |
| S3 หลัก + controls + lambda sweep | 9 | 3 | 13,107,200 | 353,894,400 |
| **training รวม** | | **56 runs** | | **518,553,600** |
| evaluation/checkpoint overhead (10%) | | | | **51,855,360** |
| **รวมก่อน buffer** | | | | **570,408,960** |

จำนวน 56 runs คือ 5 + (8x3) + (9x3) และไม่รวมการวัด benchmark แยกต่างหาก

## 4. Throughput ต่อ node ของ LANTA

ยังไม่มีสิทธิ์ submit บน LANTA ในรอบนี้ ดังนั้น 12,000 t/s เป็นค่าประมาณสำหรับวางแผน ไม่ใช่การวัดจริง:

- สมมติ 10 runs ต่อ node; แต่ละ run ใช้ประมาณ 12 threads (8 envs + learner)
- ใช้ 1,200 t/s ต่อ run เป็นค่าทำงานสำหรับการวางแผนเมื่อเทียบกับ WSL S1/S2; ยังไม่ได้วัดบน LANTA
- throughput รวมที่ใช้คำนวณ = 10 x 1,200 = **12,000 t/s**
- `scripts/lanta/bench_throughput.sbatch` จะวัดค่าจริงด้วย K=10, 20 updates ก่อนขอ quota ใหญ่

การวาง 10 runs เป็นข้อจำกัดด้าน thread ไม่ใช่การอ้างว่า LANTA จะเร็วเท่ากันทุกงาน; ผล WSL แสดงแล้วว่า
การรันพร้อมกันเกินจำนวน core ทำให้ throughput ต่อ run ลดลงมาก จึงต้องตรวจจาก benchmark จริง

## 5. Node-hours

ใช้สูตรตามแผน:

`node-hours = transitions รวม x 1.3 buffer / (throughput ต่อ node x 3,600)`

`570,408,960 x 1.3 / (12,000 x 3,600) = 17.17 node-hours` จึงปัดขึ้นเป็น
**18 node-hours (base estimate)**

ความไม่แน่นอนหลักคือ S3 ยังเป็นเพดาน 800 updates และ throughput LANTA ยังไม่ได้วัด หาก benchmark ได้เพียงครึ่งหนึ่ง
ของสมมติฐาน จะเป็นประมาณ 35 node-hours ก่อนเผื่อการแก้ recipe ดังนั้นข้อเสนอสำหรับคำขอรอบแรกคือ
**100 node-hours** เพื่อรองรับการวัด benchmark, การทดลองแก้ไข และการทำซ้ำที่ไม่ผ่าน โดยไม่อ้างว่าใช้ครบแน่นอน

## 6. Slurm scripts ที่เตรียมไว้ (ยังไม่ submit)

| ไฟล์ | งาน |
|---|---|
| `scripts/lanta/bench_throughput.sbatch` | วัด throughput ต่อ node ด้วย K runs |
| `scripts/lanta/s1_recipe.sbatch` | รัน S1 recipe หลาย seeds และ resume ได้ |
| `scripts/lanta/s2_pilot.sbatch` | fine-tune/eval S2 หลาย seeds; รองรับ anchor recipe |

ก่อน submit ต้องแทน `<project-account>`, ตรวจ partition/time limit และติดตั้ง `~/venvs/rl_fall` บน LANTA

## 7. ขอบเขตหลักฐาน

M3 ใช้ transitions จาก endpoint จริงของ M1/M2 เป็นฐาน แต่ยังไม่ใช่การยืนยัน throughput ของ LANTA
และไม่ใช่หลักฐานว่า S3 ผ่าน gate การปรับ estimate หลัง benchmark หรือหลังมีผล S3 ต้องบันทึกเป็น revision ใหม่
โดยไม่ลบตัวเลขเดิม
