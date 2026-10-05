# RL Fall benchmark prototype

โปรโตไทป์ MuJoCo แบบ planar สำหรับเปรียบเทียบ MuJoCo CPU + PPO CPU กับ
MuJoCo CPU + PPO CUDA ตาม `planning/CPU_RTX4060_Benchmark_Prototype_Plan_TH.md`.

โมเดลนี้เป็น engineering proxy ไม่ใช่แบบจำลองการบาดเจ็บมนุษย์ และผล benchmark
ไม่ใช่หลักฐานว่า policy เรียนรู้ protective falling.

## Setup

PowerShell:

```powershell
$uv = "$env:APPDATA\Python\Python314\Scripts\uv.exe"
& $uv venv --python 3.12 .venv
& $uv pip install --python .venv\Scripts\python.exe -r requirements-lock.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest
```

Linux / WSL2 (ไม่ต้องใช้ sudo; ใช้แบบเดียวกันบน login node ของ HPC ได้):

```bash
git clone <repo> ~/RL_Fall && cd ~/RL_Fall
scripts/setup_linux.sh              # สร้าง venv ที่ ~/venvs/rl_fall
scripts/run_benchmark_3d.sh         # pytest -> P1 -> P2 physics/PPO -> selection -> P3
scripts/run_benchmark_3d.sh --with-p4
```

บน WSL ให้ clone ไว้ใน Linux filesystem (`~/`) ไม่ใช่ `/mnt/c` เพราะ I/O ข้าม
ระบบไฟล์ช้ากว่า ผลรันบน Linux และ Windows ต่าง platform กัน ห้ามนำมาจับคู่เทียบกัน

## ดูท่าทางของ policy (ใช้เฉพาะตอนอยากดู)

`scripts/watch_policy.py` รันเป็น process แยกจากการเทรน จึงไม่ทำให้เทรนช้าลง ถ้าให้ path เป็นโฟลเดอร์
ระดับบน สคริปต์จะเลือก checkpoint ล่าสุดเอง และในโหมดสดจะโหลด checkpoint ใหม่ทุกครั้งที่เริ่ม episode ถัดไป
จึงดูความคืบหน้าระหว่างเทรนได้ บน Windows อ่านผลที่เทรนใน WSL ผ่าน `//wsl.localhost/Ubuntu/...` ได้โดยตรง

```powershell
$env:PYTHONPATH = "$PWD\src"
$R = "//wsl.localhost/Ubuntu/home/<user>/RL_Fall/results/stage1"
.\.venv\Scripts\python.exe scripts\watch_policy.py $R                       # หน้าต่างสด
.\.venv\Scripts\python.exe scripts\watch_policy.py $R --impulse 0.12        # แรงผลักคงที่
.\.venv\Scripts\python.exe scripts\watch_policy.py $R --passive             # ท่านิ่ง ไม่มี policy
.\.venv\Scripts\python.exe scripts\watch_policy.py $R --record out.mp4 --episodes 4
```

การอัดวิดีโอต้องติดตั้ง extra `viz` (`imageio`, `imageio-ffmpeg`) ส่วนหน้าต่างสดใช้ GPU วาดภาพ
จึงไม่ควรเปิดไว้ระหว่างรัน benchmark ที่จับเวลา

## Smoke test และ benchmark

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m rl_fall.env
.\.venv\Scripts\python.exe benchmarks\physics.py --transitions 20000 --repetitions 3
.\.venv\Scripts\python.exe benchmarks\training.py screen --devices cpu cuda --env-counts 1 4 8 --threads 1 2 4 --include-dummy-4
.\.venv\Scripts\python.exe benchmarks\select_configuration.py
.\.venv\Scripts\python.exe benchmarks\report.py
```

คำสั่ง benchmark ใช้ entry-point guard สำหรับ Windows และรันแต่ละ device
ตามลำดับเพื่อไม่ให้แย่ง CPU พร้อมกัน ดูตัวเลือกเพิ่มเติมด้วย `--help`.

หลัง P2 และเมื่อ resource preflight ผ่าน:

```powershell
.\.venv\Scripts\python.exe benchmarks\training.py confirm --env-counts 1 --primary-env-count 1 --threads 4
.\.venv\Scripts\python.exe benchmarks\training.py quality --n-envs 1 --threads 4
```

`confirm` และ `quality` จะหยุดก่อนรันเมื่อ RAM ว่างต่ำกว่า 3 GiB หรือ GPU มี
background utilization มากกว่า 10% โดยไม่ปิดโปรแกรมหรือเปลี่ยน power plan ให้ผู้ใช้.
