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
