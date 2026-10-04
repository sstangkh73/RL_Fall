# สถานะ benchmark CPU เทียบ RTX 4060

อัปเดต 3 ตุลาคม 2569

## ย้ายไป Linux และ P3-3D เสร็จ (3 ตุลาคม 2569)

รันบน WSL2 Ubuntu 24.04 (Linux-6.6.87.2-microsoft-standard-WSL2, Python 3.12.3,
torch 2.14.0+cu130, MuJoCo 3.13.0) เครื่องเดิม: CPU 16 logical, RTX 4060 ด้วย
`scripts/setup_linux.sh` และ `scripts/run_benchmark_3d.sh` source snapshot
อยู่ใน manifest ของแต่ละ run (git HEAD a938bd0 + การแก้ portability ที่ยังไม่ commit)

- tests 22/22 ผ่าน, P1-3D convergence ผ่านครบ 5 กรณี
- P2-3D physics ชุดหลัก 8 สภาวะ × 20,000 × 3: median 1,482–1,669 transitions/s
- P2-3D PPO ชุดเต็ม (warm-up 10 + measured 20) เลือก 8 envs, subproc, 4 learner threads:

| envs | threads | CPU t/s | CUDA t/s | CUDA speedup |
|---:|---:|---:|---:|---:|
| 1 | 1 | 803.0 | 349.5 | 0.435x |
| 1 | 4 | 778.4 | 344.6 | 0.443x |
| 4 | 1 | 1,714.3 | 933.5 | 0.545x |
| 4 | 4 | 1,817.3 | 848.0 | 0.467x |
| 8 | 1 | 2,109.7 | 1,308.5 | 0.620x |
| 8 | 4 | 2,401.5 | 1,369.4 | 0.570x |

- P3-3D ครบ 24/24 runs (A–D × seeds 33001–33003 × CPU/CUDA, warm-up 10 + measured 100)
  ไม่มี failed run ทุกคู่ใช้ initial-weights และ source hash ตรงกัน ผ่าน preflight gate
  และ GPU utilization ระหว่าง CPU runs มี median 0%:

| condition | CPU t/s (median) | CUDA t/s (median) | CUDA speedup median (range) |
|---|---:|---:|---:|
| A | 2,755.6 | 1,403.7 | 0.509x (0.495–0.537) |
| B | 2,574.8 | 1,321.8 | 0.513x (0.507–0.531) |
| C | 2,786.0 | 1,417.0 | 0.509x (0.502–0.515) |
| D | 2,511.9 | 1,409.7 | 0.547x (0.532–0.622) |

สรุปเชิงระบบ: บน Linux ที่ layout 8 envs, CPU PPO เร็วกว่า CUDA ประมาณ 2 เท่าในทุก condition
ยังไม่ใช่ข้อสรุป time-to-solution จนกว่า P4-3D quality gate จะผ่าน และห้ามจับคู่ตัวเลขนี้กับผล
Windows เพราะต่าง platform

รอบแรกบน WSL ถูกยกเลิกเพราะ Roblox ใช้ GPU ~99% และ CPU ระหว่างวัด ผลเก็บไว้ที่
`results/linux_wsl/benchmark_3d_confounded_roblox_20261003/` และห้ามใช้ ผลชุดที่ใช้ได้อยู่ใน
`results/linux_wsl/benchmark_3d/` (ต้นฉบับอยู่ที่ `~/RL_Fall/results/benchmark_3d` ใน WSL)

### P4-3D และ learning curve (4 ตุลาคม 2569)

P4-3D ครบ 6/6 runs (condition B, 8 envs, seeds 44001–44003, 512 updates, evaluation
64 scenarios ที่ update 0/128/256/512) paired weights ตรงกันทุกคู่ CPU ใช้ ~430 วินาที/run
(~2,440 t/s) ส่วน CUDA ใช้ ~840 วินาที/run (~1,240 t/s) และ evaluation บน CUDA ช้ากว่า
(~180 เทียบกับ ~100 วินาที)

| seed | device | mean task successes ที่ update 0 / 128 / 256 / 512 |
|---:|---|---|
| 44001 | CPU | 0.000 / 0.172 / 0.266 / 0.219 |
| 44001 | CUDA | 0.000 / 0.109 / 0.234 / 0.062 |
| 44002 | CPU | 0.000 / 0.016 / 0.156 / 0.094 |
| 44002 | CUDA | 0.000 / 0.156 / 0.188 / 0.125 |
| 44003 | CPU | 0.000 / 0.172 / 0.109 / 0.156 |
| 44003 | CUDA | 0.000 / 0.016 / 0.078 / 0.109 |

Learning curve ยาว (CPU, B, seed 55001, 12,000 updates = 24.6M transitions,
2.86 ชั่วโมง steady, 2,390 t/s) ไม่มีแนวโน้มเรียนรู้: task successes ระหว่าง train อยู่ที่
0.15–0.19 ต่อ update ตลอดตั้งแต่ช่วงแรก task reward เฉลี่ยใกล้ 0 และ evaluation success
แกว่งอยู่ระหว่าง 0.08–0.22 ต่อ episode ไม่ขยับขึ้นตามจำนวน updates ส่วน damage penalty
เป็น 0 เพราะ condition B ปิด penalty ตามที่ออกแบบไว้

ข้อสรุปตามแผนข้อ 6.5: ทั้งสองฝั่งยังไม่เรียนรู้ จึงสรุปได้แค่ benchmark ระบบ
(CPU เร็วกว่า CUDA ~2 เท่า) ยังสรุป time-to-solution ไม่ได้ และยังไม่ควรใช้ผลนี้กำหนด
งบ node-hours ของงานวิจัย ต้องทำให้ task เรียนรู้ได้ก่อน เช่น ตรวจ reward/shaping,
เพิ่มรางวัลการทรงตัว, ทำ curriculum หรือปรับ hyperparameters โดยใช้เครื่องนี้ทำรอบสั้นๆ

ผลอยู่ใน `results/linux_wsl/benchmark_3d/` และ `results/linux_wsl/learning_curve_3d/`

## การเปลี่ยนขอบเขต

ตาม amendment วันที่ 12 กันยายน งานหลักเปลี่ยนจาก planar เป็น 3D เพราะ benchmark ต้องลด
งบการรัน แต่ไม่ลดมิติฟิสิกส์จากงานวิจัยจริง ผล planar ทั้งหมดถูกจัดเป็น pipeline baseline
และไม่ใช้เลือกทรัพยากรสำหรับงานวิจัย

## หลักฐาน planar ที่เก็บไว้

- P0/P1 tests เดิมผ่าน 15 รายการ และ numerical convergence ผ่าน
- P2 physics ครบ 6 สภาวะ × 20,000 transitions × 3 repetitions
- P3 planar ครบ 24/24 runs หรือ 5,406,720 transitions ไม่มี failed run และทุกคู่ใช้
  initial-weights/source hash ตรงกัน
- planar CUDA ช้ากว่า CPU: median CPU-time/CUDA-time ของ A–D อยู่ 0.68–0.70x
- ตัวเลขนี้ตอบได้เฉพาะ workload planar เดิม ไม่ใช่ workload 3D ใหม่

## งาน 3D ที่ทำเสร็จ

- สร้าง free-root 3D MuJoCo body มวล 20 kg, 16 actuated DoF, action 16 และ observation 70
- เพิ่มการเคลื่อนที่/เอื้อม 3D, แรงผลักทุกทิศแนวนอน ณ จุดออกแรงสามมิติ และ damage หกส่วน
- แยก asset/config/source hash และ initial weights จาก planar
- tests รวมผ่าน 21/21: free root, mass/DoF, seeded reset, no initial contact,
  lateral motion, damage mapping, target masking และ finite-horizon termination
- numerical convergence 500 เทียบ 1000 Hz ผ่านเกณฑ์ damage ต่างไม่เกิน 10%
  ใน standing, low/high drop, forward fall และ lateral fall
- PPO smoke หนึ่ง update ผ่านทั้ง CPU/CUDA ด้วย initial-weights และ source hash คู่เดียวกัน
  ได้ 399.2 transitions/s บน CPU และ 215.2 transitions/s บน CUDA ตัวเลขนี้เป็น smoke
  ไม่มี warm-up และยังใช้ตัดสินผู้ชนะไม่ได้
- P2-3D physics แบบลดงบเสร็จ 8 สภาวะ × 2,000 transitions × 3 repetitions;
  median อยู่ 908.1–1,115.1 transitions/s โดยใช้ action trace hash เดียวกัน
- P2-3D PPO แบบลดงบใช้ warm-up 2 + measured 5 updates และ paired weights:

| Environments | Threads | CPU transitions/s | CUDA transitions/s | CUDA speedup |
|---:|---:|---:|---:|---:|
| 1 | 1 | 486.2 | 266.7 | 0.549x |
| 1 | 4 | 480.6 | 273.3 | 0.569x |
| 4 | 1 | 967.7 | 736.3 | 0.761x |
| 8 | 1 | 1,445.4 | 1,244.2 | 0.861x |

ตัวเลข P2 นี้ชี้ว่า 8 environments ใช้ CPU physics ได้คุ้มกว่า 1/4 และทำให้ช่องว่าง
CPU/CUDA แคบลง แต่ทุกคู่ยังเป็น screening seed เดียว ช่วงวัดสั้น และ GPU utilization พื้นหลัง
ประมาณ 25–26% จึงยังห้ามใช้เป็นผลยืนยัน

## ขั้นที่ต้องทำต่อ

1. เมื่อ GPU background ต่ำกว่า gate ให้รัน P2-3D ชุดเต็มด้วย warm-up 10 + measured 20
   เพื่อยืนยัน candidate 8 environments; physics ชุดหลักยังต้อง 20,000 × 3
2. ล็อก layout แล้วเริ่ม P3-3D ด้วย paired seeds ใหม่
3. รัน P4-3D quality gate ก่อนสรุป time-to-solution

ผลดิบ 3D อยู่ใน `results/benchmark_3d/` ส่วนผล planar เดิมยังอยู่ใน
`results/benchmark/` เพื่อรักษา audit trail
