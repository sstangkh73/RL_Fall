# แผนโปรโตไทป์เพื่อเปรียบเทียบ CPU กับ RTX 4060

วันที่ 11 กันยายน 2569 — แผนดำเนินงานประกอบ Proposal รุ่น 1.1

สถานะ: วางแผนเท่านั้น ยังไม่ได้สร้าง environment ติดตั้งชุด RL หรือรัน benchmark ตัวเลขด้านล่างเป็นงบทดลองและเกณฑ์ที่เสนอ ไม่ใช่ผลวัดความเร็ว แผนนี้ไม่แก้ผลการทดลองหรืออ้างว่าได้พิสูจน์ protective falling แล้ว

## 1 เป้าหมายและสิ่งที่ต้องตัดสินใจ

สร้าง workload ขนาดเล็กที่มีงานหลักของ RL Fall จริง เพื่อวัดว่า MuJoCo CPU ร่วมกับ PPO บน CPU หรือ PPO บน RTX 4060 ทำงานได้คุ้มกว่าบนเครื่องเดิม แล้วใช้ผลเลือก backend จำนวน environments และชนิดทรัพยากรที่ควรขอจาก HPC

ต้องตอบให้ได้สามข้อ: ส่วนใดใช้เวลามากที่สุด การใช้ CUDA ลดเวลารวมจริงหรือไม่ และความเร็วที่ได้ยังให้คุณภาพการเรียนรู้ใกล้เคียงกันหรือไม่ การวัด neural network ด้วยข้อมูลสุ่มอย่างเดียวตอบไม่ได้ว่าต้นแบบทั้งระบบเร็วขึ้นเท่าไร

ผลเปรียบเทียบหลักเป็นการเปลี่ยนอุปกรณ์ของ PPO โดยใช้ MuJoCo CPU ตัวเดียวกัน การใช้ GPU physics เป็นงานต่อยอดแยกต่างหาก จะไม่เอามาปนเป็นการเปลี่ยน hardware อย่างเดียว เอกสาร SB3 แนะนำ CPU สำหรับ PPO ที่ไม่ใช้ CNN จึงใช้ CPU เป็น baseline ที่ต้องปรับให้เหมาะสมก่อน [1]

## 2 เครื่องทดสอบและข้อจำกัดที่ตรวจพบ

| รายการ | ข้อมูลที่อ่านจากเครื่องในวันที่จัดทำ |
|---|---|
| CPU | Intel Core i5-14400F |
| Logical processors ที่ runtime เห็น | 16 ไม่ใช้แทนจำนวน physical cores |
| RAM ติดตั้ง | 16 GiB |
| GPU | NVIDIA GeForce RTX 4060 |
| VRAM ที่ driver รายงาน | 8,188 MiB |
| NVIDIA driver | 616.56 |
| ระบบปฏิบัติการที่ runtime รายงาน | Microsoft Windows 10.0.26200 เป็นเลขรุ่นระบบ ไม่ใช้เดาชื่อรุ่นการตลาด |

ข้อมูลอ่านด้วย registry เฉพาะชื่อ CPU, .NET ProcessorCount, Windows GetPhysicallyInstalledSystemMemory และ nvidia-smi หลัง CIM ถูกปฏิเสธสิทธิ์ ไม่มีการแก้ driver หรือการตั้งค่าระบบ ก่อนรันจริงต้องบันทึก RAM/VRAM ว่าง ภาระงานเบื้องหลัง และรุ่นซอฟต์แวร์อีกครั้ง

เริ่มที่ 1, 4 และ 8 environments จำนวน 16 เป็นเงื่อนไขที่เพิ่มได้เมื่อ RAM และภาระ CPU รองรับ หากหน่วยความจำว่างต่ำกว่า 3 GiB หรือมี paging ต่อเนื่อง ให้หยุดเพิ่ม workers และบันทึกว่าไม่เหมาะกับเครื่องนี้ เกณฑ์ดังกล่าวเป็นข้อกำหนดรักษาความใช้งานได้ของเครื่อง ไม่ใช่ผล benchmark ห้ามปิดโปรแกรมอื่นหรือเปลี่ยน power plan ของผู้ใช้โดยอัตโนมัติ

## 3 ขอบเขตโปรโตไทป์

ต้องสร้างส่วนต่อไปนี้ให้รันได้ก่อนวัดระบบจริง:

1. ร่างกาย planar แบบ rigid body มีศีรษะ ลำตัว แขนสองข้างและขาสองข้าง รวม 8 actuated joints พร้อมพื้น การชนและแรงผลัก ใช้ geometry เรียบง่าย เช่น capsule/box ไม่ทำภาพสมจริง
2. Damage หกส่วนที่สะสมและเปลี่ยนหน้าที่: แขนขาจำกัด torque, ลำตัวจำกัดงบแรงขับรวม, ศีรษะทำข้อมูลเป้าหมายหายพร้อม validity mask ตาม Proposal 1.1 ไม่ render ภาพกล้องและไม่ใช้ CNN
3. งานเคลื่อนฐานสลับเอื้อมเป้าหมายพร้อมรางวัลภารกิจ ไม่มีรางวัลท่ายืนหรือปกป้องศีรษะในเงื่อนไข B มี configuration เปิด/ปิดผลเสียและ penalty สำหรับ A–D
4. Control 50 Hz, physics 500 Hz หรือ 10 substeps ต่อ control transition และ episode 30 วินาทีตามแผนเดิม ไม่ reset เมื่อหกล้มหรือเสียหาย
5. Gymnasium environment, PPO training runner, checkpoint, evaluation และ log แบบ headless

การสิ้นสุด 30 วินาทีถือเป็น finite-horizon objective ที่กำหนดไว้ในงาน ต้องมี remaining-time observation และไม่ bootstrap ข้ามขอบเขตภารกิจนี้ การหยุดรันจาก infrastructure ต้องแยกจากการสิ้น episode ตามโจทย์ ตรวจ terminal observation ของ vectorized wrapper เพื่อไม่ให้ใช้ observation หลัง reset แทนสถานะสุดท้าย [2]

ค่ามวล ความทนทานและ load-to-damage mapping ต้องบันทึกและล็อกก่อนชุดจับเวลา ใช้ engineering proxy ตามข้อเสนอ ไม่มี FEM และไม่เรียกผลว่ากระดูกหักหรือสมองบาดเจ็บที่ผ่านการตรวจสอบ หากเปลี่ยนโมเดล contact/damage/task อย่างมีสาระสำคัญภายหลัง ต้อง benchmark ใหม่

ยังไม่ต้องสร้าง 3D, FEM, modular fall controller, H3 redundant-sensor training หรือทำ 40–50 final runs ของโครงการวิจัย เป้าหมายรอบนี้คือความถูกต้องของ workload และหลักฐานต้นทุนการคำนวณ การยังไม่เกิดท่าป้องกันตัวไม่ใช่เหตุให้หยุดการวัดความเร็ว แต่ทำให้ยังสรุปประสิทธิภาพการเรียนรู้ระยะยาวไม่ได้

## 4 ชุดซอฟต์แวร์และโครงสร้างงานที่เสนอ

ใช้ Python ใน environment ของโครงการแยกจาก runtime สำหรับเอกสาร พร้อม MuJoCo, Gymnasium, Stable-Baselines3, PyTorch ที่รองรับ CUDA และเครื่องมืออ่านทรัพยากร เช่น psutil เลือกรุ่น stable ที่เข้ากันได้เมื่อเริ่มพัฒนา แล้วล็อกรุ่นทั้งหมด ไม่ติดตั้งจากหน้าเอกสารรุ่น development โดยอัตโนมัติ ไม่เปลี่ยนชุด dependency ระหว่างการเปรียบเทียบ

โครงสร้างที่จะสร้างเมื่อเริ่มลงมือ:

| ตำแหน่งที่เสนอ | หน้าที่ |
|---|---|
| src/rl_fall/env.py และ assets/planar_body.xml | Environment และร่างกาย |
| src/rl_fall/damage.py และ tasks.py | ผลเสียหกส่วน ภารกิจและ observation |
| src/rl_fall/train.py | PPO และการบันทึก checkpoint |
| benchmarks/physics.py | วัด simulation ด้วย action/state ชุดเดียวกัน |
| benchmarks/training.py | จับเวลา end-to-end และ paired runs |
| benchmarks/report.py | รวมข้อมูล สรุปผลและต้นทุน |
| configs/benchmark/ | Config CPU/CUDA และตารางทดลองที่ล็อกไว้ |
| tests/ | ตรวจ semantics ของฟิสิกส์ ความเสียหายและ reset |
| results/benchmark/ | Run manifests, metrics, checkpoints และรายงาน |

รายการนี้เป็นแผนไฟล์ ไม่ใช่ไฟล์โค้ดที่สร้างแล้ว บน Windows ให้ใช้ entry-point guard และ worker creation ที่รองรับ spawn โดย process จำลองไม่สร้าง CUDA context โดยไม่จำเป็น [2]

## 5 ขั้นพัฒนาและเกณฑ์ผ่าน

| ขั้น | งาน | หลักฐานก่อนผ่าน |
|---|---|---|
| P0 | ตรวจ dependencies และสร้าง environment ขั้นต่ำ | รัน headless ได้, action/observation ผ่าน API checks, reset ทำซ้ำได้ |
| P1 | ใส่หกส่วน ภารกิจ แรงผลักและ logging | หน้าที่เสียจริงทั้งหกส่วน, ไม่ reset เมื่อชน, ไม่มีข้อมูลเป้าหมายรั่วข้าม sensor |
| P2 | ตรวจคอขวดและคัด configuration | มี physics trace และ CPU/CUDA screening แบบจับคู่ |
| P3 | จับเวลายืนยัน configuration ที่เลือก | มี 3 paired seeds, ตรวจ A–D, แยก startup กับ steady state |
| P4 | ตรวจคุณภาพการเรียนรู้และทำรายงาน | Learning curves, evaluation ที่ไม่ใช้จูน และข้อเสนอเลือกทรัพยากรพร้อมข้อจำกัด |

P1 ต้องมีการทดสอบที่ตรวจบั๊กสำคัญโดยตรง: damage ไม่ลดเอง, actuator อ่อนลงตามค่าที่ระบุ, torso cap ไม่ถูกข้าม, head damage เปลี่ยนอัตราข้อมูล, กลุ่มปิดผลเสียยัง log damage แต่หน้าที่ไม่ลด, timestep ไม่ทำให้สะสม damage เพิ่มเพราะนับถี่ขึ้น และ episode terminal/reset ไม่คืน health ก่อนเวลา

ใช้ชุดท่าตรวจครอบคลุมยืน/เคลื่อนที่ เริ่มเสียสมดุล และมีหลายส่วนสัมผัสพื้น รวมถึงสถานะเสียหายบางส่วนและมาก เก็บทุกชุดแยกกันเพื่อไม่ให้ผลเฉลี่ยจากท่ายืนอย่างเดียวแทนต้นทุนช่วงกระแทก เกณฑ์ numerical convergence เริ่มต้นใช้ตาม Proposal และต้องผ่านก่อนอ้างผลจากการล้ม

## 6 ตารางการเปรียบเทียบ

### 6.1 อุปกรณ์สองแบบที่ต้องเทียบ

| Run family | Physics | Policy inference และ PPO update |
|---|---|---|
| CPU | MuJoCo บน CPU | PyTorch CPU |
| CUDA | MuJoCo บน CPU ตัวเดียวกัน | PyTorch บน RTX 4060 |

การตั้ง device เป็น CUDA เปลี่ยนส่วน policy/update ใน SB3 และยังมีการรับส่ง observation/action กับ environment CPU ไม่ทำให้ MuJoCo ทั้งตัวไปรันบน GPU อัตโนมัติ ผลต้องรายงานด้วยชื่อสองคอลัมน์นี้เพื่อไม่ให้เข้าใจผิด

### 6.2 การคุมงบ PPO

ค่าหลัก: actor/critic MLP 128–128, float32, learning rate 0.0003, clip 0.2, GAE 0.95, gamma 0.999, minibatch 512 และ 10 epochs ไม่เปิด AMP หรือ torch.compile เฉพาะฝั่งหนึ่ง ไม่เพิ่ม network ให้ใหญ่เพื่อให้ GPU ดูคุ้ม

สำหรับ performance sweep กำหนด rollout รวม 2,048 transitions ต่อ update:

| Environments | Steps ต่อ environment | รวม transitions ต่อ update |
|---|---|---|
| 1 | 2,048 | 2,048 |
| 4 | 512 | 2,048 |
| 8 | 256 | 2,048 |
| 16 เมื่อผ่าน memory gate | 128 | 2,048 |

CPU/CUDA แต่ละคู่ใช้จำนวน environments, steps และ configuration เท่ากัน การเปลี่ยนจำนวน environments ทำให้ความยาว rollout ต่อ environment เปลี่ยน จึงอาจเปลี่ยน learning dynamics ด้วย ห้ามนำคู่ที่จำนวน environments ต่างกันมาอ้างว่าเป็นผลจาก device อย่างเดียว Appendix ของ Proposal ที่ระบุ 256 steps ต่อ environment เป็นค่าตั้งต้นการฝึก ส่วนตารางนี้กำหนดเฉพาะ benchmark sweep ก่อนล็อกค่าฝึกจริง

เริ่ม DummyVecEnv ที่ 1 environment และ SubprocVecEnv ที่ 4/8 ตรวจ DummyVecEnv เทียบ SubprocVecEnv ที่ 4 ด้วย เพราะ IPC อาจแพงกว่าฟิสิกส์ที่เบา ในขั้น diagnostic สำรวจจำนวน CPU learner threads 1, 2 และ 4 โดยจำกัด worker threads ไม่ให้ทับซ้อนเกินจำเป็น เลือกและล็อก thread/worker layout จาก screening ใช้เหมือนกันในคู่หลัก และแยกผลที่จูนแต่ละ device เป็นตารางรอง

### 6.3 P2 คัด configuration โดยยังไม่อ้างผลยืนยัน

เริ่ม physics-only test ด้วย initial states, push schedules และ action traces เดียวกัน แยกผลตามลักษณะ contact ใช้ชุดละ 20,000 control transitions และ 3 repetitions โดยยังไม่มี PPO เพื่อเห็นเวลาฟิสิกส์และการรับส่งข้อมูล หาก trace ต้อง reset ให้ใช้ schedule เดียวกัน ผลนี้เป็น diagnostic ไม่ใช้แทน end-to-end score

จากนั้นใช้เงื่อนไข B ตรวจ CPU/CUDA ที่ 1/4/8 และ 16 เมื่อผ่าน gate ใช้ seed สำหรับ screening แยกจาก P3 หนึ่ง seed ต่อ configuration อุ่น 10 updates แล้ววัด 20 updates เลือกสองจำนวน environments ที่เหมาะสมจากคู่เปรียบเทียบ และล็อก wrapper/threads ก่อน P3 ทุก diagnostic trial ต้องอยู่ใน run manifest แต่ไม่นำมารวมเป็น sample ของชุดยืนยัน

ถ้าผล screening ใกล้กัน ให้เก็บ configuration ที่เล็กกว่าไว้เป็นหนึ่งในสองตัวเลือก ห้ามตัด CPU ออกเพียงเพราะ CUDA available หรือ utilization สูง

### 6.4 P3 จับเวลายืนยันโดยเริ่มรันใหม่

ใช้ 3 paired seeds ใหม่ต่อ configuration อุ่น 10 updates แล้วจับเวลาอย่างน้อย 100 updates ตาม Proposal 1.1 รวม 225,280 transitions ต่อ run เมื่อ rollout เท่ากับ 2,048 ทุกครั้ง หาก P2 พบว่ายังไม่พ้น startup ให้ประกาศ warm-up ใหม่สำหรับทั้งคู่ก่อน P3 และคำนวณงบใหม่ สลับลำดับ CPU→CUDA และ CUDA→CPU ตามตารางที่บันทึกไว้ และรันคู่เปรียบเทียบทีละงาน ไม่รัน CPU และ GPU benchmark แย่ง CPU เครื่องเดียวกันพร้อมกัน

1. B ที่สองจำนวน environments × สอง devices × สาม seeds = 12 runs
2. A, C และ D ที่จำนวน environments ที่เลือกหนึ่งค่า × สอง devices × สาม seeds = 18 runs

รวมสูงสุด 30 runs หรือ 6,758,400 transitions รวม warm-up แต่ไม่รวม P2 หากผ่าน memory gate เพียงจำนวน environments เดียว ให้ B เหลือ 6 runs รวมทั้งชุด 24 runs และระบุข้อจำกัด จำนวน 30 เป็นแผนสูงสุดกรณีสองตัวเลือก ไม่ใช่สิทธิ์รันต่อโดยไม่หยุดเมื่อผิดปกติ

สร้าง initial network weights ชุดเดียวกันในแต่ละ paired seed ก่อนย้าย device แยก random streams สำหรับ task, disturbance, sensor dropout และ training เก็บ checkpoint/config hash โดยไม่คาดหวังให้ trajectory ที่ฝึกบน CPU/GPU เหมือนกันระดับบิต

### 6.5 P4 ตรวจว่าเร็วขึ้นโดยไม่ทำให้การเรียนรู้เสีย

ที่จำนวน environments เดียวกันที่เลือกจาก P3 ให้ฝึก B จาก initial weights ที่จับคู่กันด้วยสาม seeds ใหม่ รวม CPU/CUDA หก runs งบตั้งต้น 1,048,576 transitions ต่อ run หรือ 512 updates รวม 6,291,456 transitions ทั้งชุด ใช้ normalization และ evaluation rules เดียวกัน ระบุว่าค่านี้เป็นงบ pilot และไม่รับประกันว่าเรียนรู้ท่าป้องกันสำเร็จ

ประเมิน checkpoint ที่ update 0, 128, 256 และ 512 บน 64 scenarios ที่ล็อกไว้และไม่ใช้เลือก hyperparameters เก็บทั้ง task success, damage แยกหกส่วน และ contact distribution รายงาน learning curves ต่อ transitions และต่อ wall time โดยแยกเวลา evaluation ออกจากเวลาฝึก

ไม่ใช้การไม่มีนัยสำคัญจากสาม seeds เป็นหลักฐานว่าอุปกรณ์ให้ผลเท่ากัน หากทั้งสองฝั่งยังไม่เรียนรู้ หรือความต่างระหว่าง seeds สูง ให้สรุปได้เพียง benchmark ระบบ ยังไม่สรุป time-to-solution ของงานวิจัย หากคุณภาพดูต่าง ให้ตรวจ numerical/config mismatch ก่อนเพิ่มงบเท่ากันทั้งคู่และบันทึก amendment

P2/P3/P4 รวมกันเป็นหลายล้าน transitions จึงต้องใช้ผลคัดกรองวางแผน wall time ก่อนเริ่มชุดเต็ม ไม่ระบุล่วงหน้าว่าจะเสร็จในกี่ชั่วโมง การทดสอบการปกป้องศีรษะผ่านช่องข้อมูลสำรอง H3 ไม่อยู่ในชุด benchmark นี้

## 7 วิธีจับเวลาและวัดทรัพยากร

ตัวเลขหลักคือ completed control transitions ทุก environment รวมกัน หารด้วย wall-clock time ของช่วงที่วัด ซึ่งรวม physics, damage, observation, inference, transfer, rollout buffer, PPO updates และ logging แบบมาตรฐาน แยก control transitions ออกจาก physics substeps เพื่อไม่รายงานเร็วขึ้นสิบเท่าจากการนับคนละหน่วย

จับเวลา wall clock ด้วย monotonic high-resolution timer และ synchronize CUDA ที่ขอบต้นและท้ายช่วงจับเวลา PyTorch ระบุว่าการทำงาน CUDA เป็น asynchronous จึงต้องมี synchronization หรือ CUDA events สำหรับเวลาที่ถูกต้อง [3] ไม่ใส่ synchronize ทุก operation ในการวัด end-to-end เพราะจะเปลี่ยนรูปแบบการทำงาน ใช้ profiler/CUDA events ในรัน diagnostic แยกเมื่อหาคอขวด และไม่เอาเวลารันที่ profiler หนักมาจัดอันดับหลัก

บันทึกแยกเป็น:

- Startup: import, เปิด workers, โหลดโมเดล, CUDA initialization
- Warm-up: 10 updates แรก พร้อมรายงานว่าจนถึงจุดนั้นเวลาเสถียรหรือยัง
- Steady state: อย่างน้อย 100 updates พร้อมเวลาราย update และ contact counters
- Save/evaluation: เวลาบันทึก checkpoint และวัดคุณภาพ แยกจาก training throughput

เก็บ CPU utilization, system RAM, process-tree memory, GPU utilization, VRAM, อุณหภูมิและ clock เท่าที่ API รายงาน Sampling ตั้งต้นทุกหนึ่งวินาทีเหมือนกันทั้งคู่ RSS รวมของหลาย process อาจนับ shared memory ซ้ำ ต้องติดป้ายวิธีวัด ใช้ system available RAM ประกอบ ไม่เรียกผลรวม RSS ว่าหน่วยความจำจริงที่ไม่ซ้ำ

ผลที่ไม่มี power meter ทั้งเครื่องไม่ใช้คำนวณว่าระบบใดประหยัดไฟกว่า อาจรายงาน GPU power ที่อ่านได้เป็น telemetry เฉพาะ GPU พร้อมข้อจำกัด ไม่เปรียบกับ CPU package หรือค่า TDP แบบคนละฐาน

Main runs ไม่เปิด viewer ไม่บันทึกวิดีโอและไม่เขียน contact ทุก substep ลงดิสก์ เก็บ summary/counters แบบเดียวกัน และทำ detailed traces แยก หาก run ถูกแทรกด้วยงานหนัก มี thermal throttling, OOM หรือ solver failure ให้เก็บ log และเหตุผล ไม่ลบผลเฉพาะฝั่งที่ช้า หากรันไม่ครบหน้าต่างจับเวลาไม่รวมกับ complete runs

## 8 การสรุปผลและเกณฑ์เลือก

คำนวณ speedup ของ CUDA ภายในแต่ละคู่เป็นเวลาของ CPU หารด้วยเวลาของ CUDA รายงานค่าราย seed, median และช่วงต่ำสุด–สูงสุด พร้อมตารางทั้งสองอุปกรณ์ ไม่ใช้จำนวน updates เป็นจำนวนตัวอย่างอิสระของความเหนือกว่าทางสถิติ

| ผลที่พบ | ข้อสรุปที่อนุญาต |
|---|---|
| CPU เร็วกว่าและคุณภาพอยู่ในระดับใกล้กัน | ใช้ CPU และพิจารณา CPU HPC สำหรับรันหลาย seeds หากเครื่องเดิมไม่ทัน |
| CUDA ลดเวลารวมซ้ำได้และยังเรียนรู้ได้ | ใช้ RTX 4060 สำหรับ configuration นี้ ไม่อนุมานว่า A100 จะเร็วตามสัดส่วนสเปก |
| เร็วเฉพาะ neural-network update แต่เวลารวมไม่ดีขึ้น | ไม่อ้างประโยชน์ end-to-end ของ GPU; ตรวจ simulation/IPC/transfer |
| ผลเร็วช้าสลับไปมา หรือคุณภาพยังไม่ชัด | ยังไม่ตัดสินผู้ชนะ ใช้ setup ที่เสถียรและวัดเพิ่มเฉพาะสิ่งที่ยังไม่แน่นอน |
| Physics เป็นคอขวดหลักหลังปรับ CPU แล้ว | เสนอแผน GPU physics แยก โดยตรวจความเทียบเท่าก่อน |

คำนวณเวลาชุดงานวิจัยในเครื่องเดิมจากจำนวน transitions หารด้วย throughput ที่วัดจริง บวก warm start, startup, evaluation, checkpoint และ buffer ที่แจกแจง ใช้ขอบเขตจาก runs ที่เร็วและช้าเป็นช่วงประมาณการ ไม่ใช้ค่าเฉลี่ยสั้น ๆ ค่าเดียวรับรองงบทั้งโครงการ จำนวน runs อ้างอิง Proposal คือ H1 40 runs และ H3 เพิ่ม 10 runs เมื่อทำระยะยืนยัน

การขอ HPC ต้องแนบคอขวดที่พบ จำนวน CPU cores/RAM หรือ GPU/VRAM ที่ต้องใช้ จำนวนงานพร้อมกัน และข้อจำกัดเวลาของเครื่องเดิม หลังได้บัญชีต้อง benchmark เครื่องเป้าหมายใหม่ หาก CPU ชนะในเฟสนี้ ไม่ได้แปลว่า GPU physics จะไม่มีประโยชน์ในเฟสใหญ่ขึ้น เอกสาร MJX ปัจจุบันแยก JAX และ Warp implementations ซึ่งต้องเลือกและตรวจ compatibility ของโมเดลต่างหาก [4]

## 9 สิ่งที่ต้องส่งมอบเมื่อทำโปรโตไทป์เสร็จ

1. Environment หกส่วนและ smoke/semantic checks ที่ผ่าน พร้อม dependency lock และวิธีรันซ้ำ
2. ตาราง config/run manifest ระบุ stage, device, physics backend, seed, wrapper, environments, threads, network, timestep และ hashes
3. ข้อมูลดิบ metrics.csv/JSONL และ resource logs พร้อมสถานะ complete/failed/interrupted ของทุกรัน
4. รายงานเปรียบเทียบ CPU/CUDA รวม learning curves และตารางคอขวด โดยไม่มีช่องผลวัดที่แต่งเติม
5. ข้อสรุปเลือกทรัพยากร หรือระบุว่าอะไรยังไม่พอจะเลือก พร้อมประมาณการเวลาที่มีที่มา

ถือว่าจบงาน benchmark เมื่อมีข้อมูลที่ทำซ้ำได้ของคู่ CPU/CUDA และรายงานข้อจำกัดครบ ไม่ต้องรอให้พิสูจน์สมมติฐานทางวิจัยทั้งหมด แต่จะไม่ใช้ผลจากโปรโตไทป์ที่ยังผิดด้านฟิสิกส์หรือข้ามงาน damage ไปอ้างต้นทุนของ RL Fall ฉบับเต็ม

## แหล่งอ้างอิงวิธีการ

[1] [Stable-Baselines3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html) — CPU guidance, rollout configuration และ PPO interface.

[2] [Stable-Baselines3 Vectorized Environments](https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html) — Windows multiprocessing, auto-reset และ terminal observation.

[3] [PyTorch CUDA semantics](https://docs.pytorch.org/docs/main/notes/cuda.html) — asynchronous execution และ timing.

[4] [MuJoCo XLA](https://mujoco.readthedocs.io/en/stable/mjx.html) — GPU implementations และข้อกำหนดของ backend.

เอกสารเว็บใช้ตรวจแนวทาง ณ วันที่จัดทำ รุ่นซอฟต์แวร์ที่จะติดตั้งจริงต้องเลือกและล็อกภายหลัง ไม่ใช้เลขรุ่นหน้า master/main เป็นข้อกำหนด dependency โดยอัตโนมัติ
