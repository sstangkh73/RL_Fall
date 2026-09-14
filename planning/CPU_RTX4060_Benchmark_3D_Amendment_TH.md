# Amendment: เปลี่ยน benchmark หลักเป็นงาน 3D

วันที่ 12 กันยายน 2569

สถานะ: ใช้แก้ขอบเขตในแผนวันที่ 11 กันยายน 2569 เฉพาะจุดที่ขัดกัน

## เหตุผลและผลต่อหลักฐานเดิม

เป้าหมายของ benchmark คือประมาณต้นทุนของงานวิจัย RL Fall ตอนทำจริงโดยลดขนาดการรัน
ไม่ใช่ลดมิติทางฟิสิกส์ ดังนั้นข้อความเดิมที่กำหนดร่างกาย planar และระบุว่ายังไม่ต้องสร้าง 3D
ถูกยกเลิก ผล P2/P3 ของ planar ที่รันไปแล้วคงไว้เป็นหลักฐานตรวจ pipeline, paired weights,
logging และระบบจับเวลาเท่านั้น ห้ามใช้เลือก CPU เทียบ RTX 4060 สำหรับงานวิจัยฉบับจริง

benchmark หลักใหม่ต้องใช้ร่างกาย 3D ที่มี free root 6 DoF, ข้อต่อขับเคลื่อน 16 DoF,
contact ทุกทิศ, การล้มไปข้างหน้า/ด้านข้าง/การบิด, เป้าหมายการเคลื่อนที่บนระนาบ 2D
และเป้าหมายเอื้อมในปริมาตร 3D ขณะเดียวกันยังคง damage หกส่วน เงื่อนไข A–D,
50 Hz control, 500 Hz physics และ episode 30 วินาที

การลดสเกลในรอบพัฒนาให้ลดจำนวน transitions, updates, seeds และ repetitionsเท่านั้น
ห้ามลด 3D เป็น planar ห้ามปิด contact/damage/task และห้ามขยาย neural network เฉพาะ CUDA
เพื่อทำให้ GPU ดูเร็วขึ้น

## คู่เปรียบเทียบหลัก

| Run family | Physics | Policy inference และ PPO update |
|---|---|---|
| CPU | MuJoCo 3D บน CPU | PyTorch CPU |
| CUDA | MuJoCo 3D บน CPU ตัวเดียวกัน | PyTorch บน RTX 4060 |

แม้เป็นฉาก 3D MuJoCo ปกติในงานนี้ยังใช้ CPU การตั้ง `device=cuda` ย้ายเฉพาะ MLP PPO
ไป RTX 4060 ส่วน GPU physics เช่น MJX เป็นการทดลองอีก backend หนึ่ง ต้องตรวจ feature compatibility
และความเทียบเท่าของผลก่อนเปรียบเทียบ ห้ามเรียกว่าเป็นคู่ hardware-only เดียวกับตารางข้างบน

## โมเดล 3D ที่ล็อกสำหรับ benchmark

- ร่างกายสูงอ้างอิง 1.2 เมตร มวลรวม 20 กิโลกรัม geometry แบบ box/capsule/sphere
- ไหล่และสะโพกข้างละ 3 แกน ศอกและเข่าข้างละ 1 แกน รวม action 16 ค่า
- free root มี translation และ rotation อย่างละ 3 แกน
- observation 70 ค่า: joint state, base velocity 6 แกน, gravity ใน body frame,
  task/target พร้อม validity mask, previous action, damage และ remaining time
- MLP actor/critic 256–256 ใช้เหมือนกันทั้ง CPU/CUDA เพื่อรองรับ input/output ที่เพิ่มขึ้น
- แรงผลักสุ่มทิศรอบแนวนอนและจุดออกแรงสามมิติบนลำตัว จึงสร้าง translation, roll, pitch และ yaw
- damage ยังเป็น engineering proxy ที่ไม่ผ่านการตรวจสอบทางการแพทย์

รายละเอียดตัวเลขถูกล็อกใน `configs/benchmark/base_3d.json` และ
`configs/benchmark/model_3d_v0_1.json` การเปลี่ยน geometry, DoF, contact, task,
damage หรือ network หลังเริ่ม P2-3D ต้องเริ่มชุดจับเวลาหลักใหม่

## Gate และลำดับรันใหม่

1. P0/P1-3D: API/seed/no-initial-contact tests, ทดสอบการเคลื่อนแกนด้านข้าง,
   forward/lateral fall และ numerical convergence 500 เทียบ 1000 Hz
2. P2-3D physics: ใช้ action trace เดียวกันใน standing, moving, forward fall,
   lateral fall, twisting, multi-contact และ damage สองระดับ รอบย่อส่วนทำได้เพื่อประเมินเวลา
   แต่ชุดหลักยังใช้ 20,000 transitions × 3 repetitions
3. P2-3D PPO: condition B, paired initial weights, เริ่ม 1/4/8 environments ตาม memory gate
   รอบ smoke ลด update ได้ แต่ configuration selection ต้องใช้ warm-up 10 + measured 20
4. P3-3D: ใช้ seeds ใหม่สามคู่ต่อ configuration, warm-up 10 + measured 100,
   สลับลำดับ CPU/CUDA และตรวจ A–D ตามแผนเดิม
5. P4-3D: ตรวจ learning quality ก่อนสรุป time-to-solution หรือเลือกทรัพยากรขั้นสุดท้าย

จนกว่า P3-3D และ quality gate จะเสร็จ ข้อสรุปที่อนุญาตมีเพียงผล smoke/diagnostic
ห้ามใช้ผล planar หรือรอบ 3D สั้นหนึ่งครั้งเป็นคำตอบสุดท้ายว่า CPU หรือ GPU เหมาะกว่า
