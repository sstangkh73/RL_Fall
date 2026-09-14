# สถานะ benchmark CPU เทียบ RTX 4060

อัปเดต 12 กันยายน 2569

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
