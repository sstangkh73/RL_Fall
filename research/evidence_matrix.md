# ตารางหลักฐาน RL Fall

ตรวจถึง 10 กันยายน 2026 — อ่านร่วมกับ [รายงานหลัก](./prior_art_review_th.md)

**หลักการอ่าน:** “ยังไม่แสดง” หมายถึงไม่พบการสาธิตกลไกนั้นในส่วนที่ตรวจ ไม่ใช่รับรองว่าไม่มีอยู่ใน code หรือทุกเวอร์ชันของงาน “damage dynamics” ในที่นี้ต้องเปลี่ยนความสามารถทำงานของ agent; การบันทึก contact force หรือ health score อย่างเดียวไม่พอ

ระดับหลักฐาน: **M** อ่านวิธี/สมการ/ส่วนทดลองที่เกี่ยวข้องจากต้นฉบับ; **A** บทคัดย่อหรือ metadata ต้นฉบับ; **P** เว็บไซต์โครงการหรือ repository; **I** เนื้อหาแหล่งต้นฉบับที่เข้าถึงผ่านดัชนีเว็บ ไม่ใช่หน้าเต็มที่เปิดสำเร็จ ระดับนี้อธิบายสิ่งที่ตรวจ ไม่ใช่คะแนนคุณภาพงาน

## การล้ม สมดุล และฟื้นตัว

| งาน / ปีที่อ้าง | กลไกที่พบ | จุดตรวจสำคัญ | ผลต่อโจทย์ | หลักฐาน |
|---|---|---|---|---|
| [Learning to Predict Humanoid Fall](https://www.cse.iitb.ac.in/~shivaram/papers/kg_ijhr_2011.pdf), 2011 | ตัวทำนายเทียบความสามารถ balance controller | formulation และผล false positives / lead time | คู่แลกเปลี่ยน FAR–เวลาแจ้งล่วงหน้ามีมาก่อน | M |
| [Learning a Unified Control Policy for Safe Falling](https://arxiv.org/abs/1703.02905), 2017 | mixture of actor-critics; เลือก expert ตาม value | abstract | unified falling มีแล้ว แต่ไม่ใช่ pure monolithic controller | A |
| [Learning Arm-Assisted Fall Damage Reduction and Recovery](https://arxiv.org/html/2303.05486v1), 2023 | policy เดียวช่วงฉุกเฉิน; time-varying training rewards | §III-A, reward formulation, §IV | รวม mitigation/recovery แล้ว; มีการส่งต่อจาก nominal controller | M |
| [Guardians as You Fall](https://arxiv.org/html/2310.04828v1), 2023 preprint | planner + mode transition/recovery policies | §III โดยเฉพาะ planner | baseline สถาปัตยกรรมแยก; modes ถูกกำหนดไว้ | M |
| [FRASA](https://arxiv.org/html/2410.08655v1), 2024 | end-to-end recovery/stand-up; symmetric actions | §IV และ §V-C | โจทย์ย่อฝึกได้เร็ว แต่ไม่ใช่ injury emergence | M |
| [FIRM](https://arxiv.org/html/2511.07407v1), 2025 preprint | demonstrations → RL skills → diffusion memory | method pipeline | หักล้างคำว่า “ทุกงานมี classifier+balance+fall” | M |
| [Robot Crash Course](https://arxiv.org/html/2511.10635v1), 2025 | goal-conditioned falling; impact/style objectives | method/reward และ experiments | ท่าล้มอ่อนแรง/มีสไตล์มี prior art แล้ว | M |
| [SafeFall](https://arxiv.org/html/2511.18509v1), 2025 | GRU predictor + mitigation policy; regional reward weights | reward design, training, detection evaluation | damage priorities ถูกกำหนดได้; ยังไม่ใช่ task-only | M |
| [Discovering Self-Protective Falling Policy](https://arxiv.org/html/2512.01336v1), 2025 | reward/curriculum ค้นพบท่าค้ำ | reward และ §V-E | ไม่มี demo ก็เกิดท่าได้; ยังสลับ walking/fall ในการทดลอง | M |
| [VIGOR v2](https://arxiv.org/html/2602.16511v2), 2026 | visual policy, teacher/student, sparse goals | §III-C | deploy unified แต่ training มี priors และ safety terms | M |
| [Embedding Classical Balance Control Principles](https://arxiv.org/html/2603.08619v1), 2026 | single actor balance/step/fall/stand; physics-guided shaping | §III-E Eq.1–12; §III-F; results | ใกล้โจทย์ architectural emergence โดยตรง แต่ไม่ใช่ damage consequences only | M |
| [Unified Walking, Running, and Recovery](https://arxiv.org/html/2605.18611v1), 2026 | actor เดียว; AMP discriminators มี training gate | §III-A–D Eq.1–5 | ไม่มี runtime switch ไม่เท่ากับไม่มี threshold ระหว่างฝึก | M |
| [Multi-policy Falling Ballbot — PDF](https://www.codit2025-virtual-event.com/web/content/1251?download=true&unique=85e933f7d1b6fd18c5d94e5300d42d1d648cd09a), 2025/2026 | cluster ท่าเริ่มต้น; expert เดียวตลอด fall | เปรียบเทียบ single/multi/curriculum และ terminal cost | single vs multi มีแล้ว; ไม่ใช่ balance→protective transition | M |
| [Failing Gracefully / FailBench](https://arxiv.org/html/2608.05313v1), 2026 | failure injection; ประเมินโอกาส interaction × severity | benchmark/formulation | เกี่ยวข้องกับการประเมิน failures; ไม่ใช่หลักฐาน task-only RL emergence | M |

## ความเสียหาย หน้าที่ร่างกาย และแรงจูงใจ

| งาน / ปี | กลไกที่พบ | สิ่งที่ยังต่างจากคำถามหลัก | ตำแหน่ง / หลักฐาน |
|---|---|---|---|
| [Prolonging Tool Life](https://arxiv.org/html/2507.17275), เริ่ม preprint 2025; ใช้ฉบับปัจจุบัน | FEA stress → fatigue/RUL → reward | มี longevity reward โดยตรง; เป็นเครื่องมือ ไม่ใช่ fall protection ของร่างกาย | §III-B, §IV-B Eq.10–16 / M |
| [Evolving Afferent Architectures](https://arxiv.org/html/2602.04807v1), 2026 | cumulative knee damage; evolved afferents + PPO | inner/outer objectives หัก damage; action intensity 1D | Eq.4–5 และ §6 / M |
| [OopsieVerse](https://arxiv.org/html/2606.31993v1), 2026 | mechanical/thermal/fluid damage benchmark | RL มี penalty; endogenous body-function impairment ยังไม่ยืนยันจากส่วนที่อ่าน | RL experiment §V-B / M |
| [Health Aware Control Strategy](https://arxiv.org/abs/2010.09269), MED 2019; arXiv 2020 | degradation/RUL-aware motor control | objective คำนึงอายุใช้งาน; ไม่ใช่ protective fall | abstract / A |
| [Reset-free Trial-and-Error Learning for Robot Damage Recovery](https://arxiv.org/abs/1610.04213), 2016 | ปรับตัวหลัง damage โดยไม่ต้อง reset ทุก trial | damage ถูกใส่จากภายนอก; ไม่ได้เรียนรู้ป้องกันก่อนเกิด | abstract / A |
| [SMiRL](https://arxiv.org/pdf/1912.05510), preprint 2019 / ICLR 2021 | intrinsic surprise minimization; stabilization/hazard avoidance | ไม่ใช่ reward-free หรือ external-task-only; reset มีผล | objective และ Appendix A / M |
| [Empowerment As Replacement for the Three Laws of Robotics](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2017.00025/full), 2017 | intrinsic empowerment เกี่ยวข้องกับ self-preservation | objective ถูกเลือกไว้; ไม่ใช่ tissue damage/falling experiment | formulation/examples / M |
| [Optimal Policies Tend To Seek Power](https://proceedings.neurips.cc/paper/2021/file/c26820b8a4c1b3c2aa868d6d57e14a79-Paper.pdf), NeurIPS 2021 | ทฤษฎี optimal policy รักษาทางเลือกใน MDP ตามสมมติฐาน | ไม่รับประกันการเรียนรู้ของ RL ข้อมูลจำกัดหรือหุ่นจริง | abstract/formal scope / A |
| [The Contingencies of Physical Embodiment Allow for Open-Endedness and Care](https://arxiv.org/html/2510.07117v1), 2025 | framing embodiment, vulnerability และ care | แนวคิด; ไม่พบผลทดลองร่างกายแตกหักแล้วเรียนรู้ล้ม | เนื้อหาทฤษฎี/ข้อเสนอ / M |

## FEM และแบบจำลองชีวกลศาสตร์

| งาน / เครื่องมือ | สิ่งที่ทำได้ตามหลักฐาน | สิ่งที่ไม่ควรอนุมาน | หลักฐาน |
|---|---|---|---|
| [Soft Robots Learn to Crawl](https://arxiv.org/pdf/2202.04575), 2022 | FEM + model order reduction + RL; sim-to-real soft robots | ไม่ยืนยัน whole-body fracture model | §IV และ appendix; [project](https://sites.google.com/ttic.edu/evolving-soft-robots) / M, P |
| [SofaGym](https://github.com/SofaDefrost/SofaGym), [บทความ](https://doi.org/10.1089/soro.2021.0123) | SOFA environments เชื่อม RL | ไม่ใช่ throughput benchmark ของร่างกายที่เสนอ | repository/documentation / P |
| [Sim-to-Real Gentle Manipulation](https://arxiv.org/html/2510.25405v1), 2025 | MPM, stress penalty, rigid-to-deformable curriculum | MPM ไม่ใช่ FEM; object care ไม่ใช่ task-only self-care | methods/reward / M |
| [Computationally Efficient Full Human Body FEM](https://www.sciencedirect.com/org/science/article/pii/S1538958821001363), 2015 | detailed/simplified GHBMC models; runtime trade-off | รุ่น simplified ไม่ได้ตั้งใจใช้ทำนาย injury; benchmark เก่าไม่ใช่เวลา GPU ปัจจุบัน | introduction/discussion จากต้นฉบับที่ index / I |
| [Whole-body Musculoskeletal Standing and Falling](https://arxiv.org/html/2506.09383v1), 2025 | MuJoCo muscle model; MPPI/PD; induced weakness | โมเดลกล้ามเนื้อจำนวนมากไม่เท่ากับ FEM fracture | model/control method / M |

## แหล่งเสริมที่ไม่ใช้เป็นข้อพิสูจน์ความใหม่หลัก

- [Light REACT](https://www.lightorigins.com/en/blog/light-react): ข้อมูลผู้พัฒนาเกี่ยวกับ recovery/locomotion/crawling ภายใต้ damage ที่กำหนดไว้ มี teachers, distillation และ preference reward; ระดับ I/P เปิดหน้าเต็มไม่สำเร็จ ไม่ถือเป็น peer-reviewed evidence
- [Synthesising integrated robot behaviour through reinforcement learning for homeostasis](https://doi.org/10.1101/2024.06.03.597087): พบจาก metadata และเว็บไซต์ผู้เขียน แต่เปิด bioRxiv เต็มไม่สำเร็จ จัดเป็น lead สำหรับตรวจเพิ่ม ไม่ใช้รายละเอียดจากสำเนาบุคคลที่สามเป็นฐานคำตัดสิน
- [Evaluation of physical damage associated with action selection strategies in reinforcement learning](https://www.sciencedirect.com/science/article/pii/S240589631731724X), 2017: งานข้างเคียงเรื่องผล damage จาก exploration; ไม่ใช้ยืนยันสถาปัตยกรรมภายในที่ไม่ได้ตรวจเต็ม
- [MuJoCo deformable objects](https://mujoco.readthedocs.io/en/stable/modeling.html#deformable-objects): ใช้ตรวจความหมายของ flex/deformation; การมี deformable solver ไม่เท่ากับมีโมเดล injury ที่สอบเทียบแล้ว
- [FEBio software paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC3705975/): แหล่งซอฟต์แวร์ biomechanics สำหรับศึกษาต่อ ไม่ใช่ environment RL Fall สำเร็จรูป

## ข้อสรุปจากการจัดหมวด

งานเดิมครอบคลุมแต่ละองค์ประกอบมากแล้ว แต่ในชุดที่ตรวจยังไม่พบงานทดลองที่รวม **endogenous persistent damage ของร่างกาย + ผลต่อหน้าที่ในอนาคต + task-only reward + anticipatory protective falling** แล้วแยกเหตุด้วย ablation ที่ตรงคำถามนี้

การไม่พบดังกล่าวให้เหตุผลสำหรับ pilot เท่านั้น ต้องไม่แปลงเป็นคำรับรอง “world first” การเพิ่มเงื่อนไขเฉพาะจำนวนมากไม่ทำให้โครงการมีคุณค่าโดยอัตโนมัติ; ผลทดลองต้องตอบกลไกหรือขอบเขตที่ผู้อื่นนำไปใช้ได้

