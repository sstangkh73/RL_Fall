# ขอบเขตการค้นและสิ่งที่ยังไม่ยืนยัน

วันที่ตรวจ: **10 กันยายน 2026**

ไฟล์นี้บันทึกวิธีคัดหลักฐานของ [รายงานหลัก](./prior_art_review_th.md) ไม่ใช่รายการผลค้นหาทั้งหมด ไม่ได้รัน simulator หรือทำซ้ำผลของบทความ

## เป้าหมายการค้น

ตรวจความซ้ำซ้อนของแนวคิดสามระดับ:

1. การเรียนรู้ protective falling และการเปลี่ยนจาก balance เป็น falling ด้วย policy เดียว
2. การเรียนรู้ self-protection ผ่านความเสียหายที่ลดความสามารถทำภารกิจในอนาคต โดยไม่ให้ damage penalty ตรง
3. การใช้ FEM/soft-body/damage simulation ร่วมกับ RL และข้อจำกัดด้าน compute

การตีความข้อเสนอ “ให้ AI จัดการเองว่าจะใส่ใจดาเมจแค่ไหน” ในรายงานใช้เวอร์ชันที่ทดสอบได้เข้มที่สุด คือ external task reward เพียงอย่างเดียวและ damage เปลี่ยน dynamics หากตั้งใจให้ pain signal เป็น reward ด้วย โครงการจะใกล้ SafeFall, health-aware RL และ Evolving Afferent Architectures มากขึ้น

## วิธีติดตามหลักฐาน

- เริ่มจากงานที่ระบุในโจทย์: fall prediction ปี 2011, SafeFall และ ballbot
- ตามงาน unified fall/recovery ทั้งก่อนและหลัง 2025 รวมถึง FIRM, VIGOR, FRASA และงานมีนาคม/พฤษภาคม 2026
- ตรวจ reward equations, architecture, episode termination, demonstrations และ deployment switching ของงานที่ใกล้
- ขยายไป health-aware control, tool wear, damage-aware manipulation และแรงจูงใจ intrinsic
- ตรวจ FEM RL, reduced models และ full human body FEM เพื่อไม่สรุป feasibility จากภาพ simulation
- ตรวจแหล่งล่าสุดที่พบถึงช่วงสิงหาคม–กันยายน 2026; ไม่อ้างว่าครอบคลุมบทความทั้งหมดที่เผยแพร่ถึงวันนั้น

## ตัวอย่างคำค้นที่ใช้จริง

คำค้นเหล่านี้เป็นส่วนหนึ่งของการค้น ไม่ใช่ exhaustive query log:

```text
reinforcement learning humanoid falling irreversible damage task reward self preservation injury single policy
"reinforcement learning" "irreversible" "damage" robot self preservation
"reinforcement learning" "injury" "task reward" falling
"reinforcement learning" "body damage" reward
"robot" "damage" "without" "penalty" "self-preservation" reinforcement
"reinforcement learning" "fragile" "body" "damage" locomotion
"reinforcement learning" "persistent damage" robot
"reinforcement learning" "self-preservation" "task" physics
"Development of a computationally efficient full human body" "24" "48"
"Soft Robots Learn to Crawl" "reduced" finite element
"Synthesising integrated robot behaviour" homeostasis Yoshida
Optimal Policies Tend to Seek Power NeurIPS 2021 Turner paper
```

นอกจากนี้ใช้ชื่อบทความตรง เปิดต้นฉบับจาก arXiv/ผู้เขียน และค้นส่วน reward, episode, training และข้อจำกัดในเอกสาร ไม่ถือผลจากเว็บสรุป AI หรือ social media เป็นหลักฐานทางเทคนิคสุดท้าย

## การคัดออกและการไม่รวมเป็นข้อพิสูจน์หลัก

- งานลุกขึ้นจากพื้นอย่างเดียวไม่ถือว่าพิสูจน์ลดความเสียหายระหว่างตก
- งานที่ disable ข้อ/ขาจากภายนอกแล้วให้เรียนรู้ชดเชยไม่ถือว่าพิสูจน์การป้องกันก่อน self-caused damage
- งานใช้ damage penalty แม้คำนวณจากฟิสิกส์ ไม่ถือว่า task-only
- ข้อเสนอ self-preservation ทางทฤษฎีไม่ถือว่าได้ทำหุ่นยนต์ล้มพร้อม tissue damage แล้ว
- เว็บไซต์ demo ไม่ถือว่า simulator มี irreversible injury หากเอกสารไม่ระบุ
- ไม่เปรียบเทียบ success rate ข้ามงานที่นิยาม success ต่างกัน
- ไม่ยกตัวเลข GPU-hours ของงานหนึ่งไปทำนาย runtime ของ hardware อื่น

## จุดที่ต้องเก็บความไม่แน่นอนไว้

| จุด | สถานะ |
|---|---|
| ความใหม่ของ architectural switching กว้าง ๆ | มี prior art ตรงเพียงพอที่จะไม่ใช้เป็นข้ออ้างหลัก |
| task-only + functional damage + protective falling | ยังไม่พบการทดสอบตรงในชุดหลักฐานนี้; ไม่ใช่พิสูจน์ไม่มี |
| code มี damage-to-dynamics ที่บทความไม่อธิบายหรือไม่ | ไม่ได้ audit code ทุก repository |
| งาน 2017 Unified Safe Falling และ Health Aware Control | บางข้ออาศัย abstract; จำกัดคำอ้างตามนั้น |
| ballbot ปีเผยแพร่ | ไฟล์อยู่บน CoDIT 2025 แต่ระเบียนมหาวิทยาลัยระบุ 2026 |
| SMiRL ปี | แยก preprint 2019 จากฉบับ ICLR 2021 |
| Prolonging Tool Life ชื่อ | ฉบับก่อนใช้ Non-Specific Tools; รายงานใช้ชื่อฉบับปัจจุบัน General-purpose Tools |
| Robot Crash Course รหัส | ใช้ arXiv 2511.10635; 2508.08241 เป็น BeyondMimic ซึ่งเป็นคนละงาน |
| BioRxiv homeostasis | พบ metadata; เปิดต้นฉบับเต็มไม่สำเร็จ |
| Light REACT | เนื้อหาแหล่งผู้พัฒนาจากดัชนี; เปิดหน้าเต็มไม่สำเร็จ; ไม่จัดเป็น peer-reviewed |
| full-body FEM benchmark | ตัวอย่างปี 2015/configuration เฉพาะ; ไม่ใช่ benchmark เครื่องโครงการ |
| feasible protective policy ในร่างกายที่จะสร้าง | ยังไม่ทดสอบ |
| training speed และ VRAM ของ RL Fall | ยังไม่ benchmark |

## สิ่งที่ควรตรวจต่อหากผ่าน pilot

ก่อนใช้คำอ้างความใหม่ในข้อเสนอตีพิมพ์ ควรค้นซ้ำชื่อและ citations ของงานใกล้ที่สุด โดยเฉพาะ Embedding Classical Balance Control Principles, FIRM/VIGOR, Prolonging Tool Life, Evolving Afferent Architectures และงาน damage-aware benchmark ใหม่ ตรวจ code ของ baseline ที่เลือกจริงและบันทึก commit/version

การค้นต่อควรตอบข้อที่เปลี่ยนการตัดสินใจ เช่น มีผล ablation แบบ task-only อยู่ใน supplement หรือไม่ และความเสียหายของ simulator นั้นลดหน้าที่จริงหรือเป็นเพียง score ไม่จำเป็นต้องสะสมรายการบทความไกลโจทย์โดยไม่เพิ่มหลักฐาน

