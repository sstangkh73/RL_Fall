# ตัวตัดสินว่า "เสร็จแล้ว" : exit 0 = ผ่าน, อย่างอื่น = ยังไม่ผ่าน
# AI ห้ามแก้ไฟล์นี้ (ถ้าถูกแก้ ลูปจะหยุด)
#
# 1. tests ของโปรเจกต์ต้องผ่าน (รันใน WSL ด้วย venv ที่ใช้เทรน)
# 2. milestones M1–M4 ใน GOAL.md ต้องผ่าน (tools/check_goal.py อ่านไฟล์ผลจริง)
#    สรุปผลอยู่ที่ reports/goal-status.md

param([string]$Distro = 'Ubuntu')

$root = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$wslRoot = (wsl.exe -d $Distro -- wslpath -a $root).Trim()

Write-Host "=== pytest (WSL, $wslRoot)"
wsl.exe -d $Distro -- bash -lc "cd '$wslRoot' && PYTHONPATH=src ~/venvs/rl_fall/bin/python -m pytest -q -p no:cacheprovider"
$tests = $LASTEXITCODE

Write-Host "`n=== milestones"
wsl.exe -d $Distro -- bash -lc "python3 '$wslRoot/auto-loop/tools/check_goal.py' --win-root '$wslRoot' --wsl-repo ~/RL_Fall"
$goal = $LASTEXITCODE

Write-Host "`ntests exit=$tests  goal exit=$goal"
if ($tests -eq 0 -and $goal -eq 0) { exit 0 }
exit 1
