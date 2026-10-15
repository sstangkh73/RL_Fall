<#
  รันงานยาว (เช่นเทรน) ใน WSL แบบ background แยกจาก Claude แล้วจับเวลาให้อัตโนมัติ

  ใช้:  pwsh -NoProfile -File auto-loop/tools/wsl-job.ps1 -Name m1-seed63001 -Command "scripts/run_stage1_v1_recipe.sh 63001"
        -Command  คำสั่ง bash ที่รันใน ~/RL_Fall (clone ใน WSL)
        -NoSync   ไม่ต้อง copy โค้ดจาก C:\RL_Fall ไป ~/RL_Fall ก่อนรัน

  ก่อนรันจะ copy src/ scripts/ tests/ configs/ assets/ pyproject.toml ไป ~/RL_Fall (ไม่ลบไฟล์ปลายทาง)
  ผล: auto-loop/reports/jobs/<id>.{cmd,json,log,heartbeat} และแถวใน auto-loop/reports/jobs.md เมื่อจบ
  ดูสถานะ: pwsh -NoProfile -File auto-loop/tools/jobs.ps1
#>
param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$Command,
    [string]$Distro = 'Ubuntu',
    [switch]$NoSync
)
$ErrorActionPreference = 'Stop'
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture

$loopDir = Split-Path $PSScriptRoot -Parent
$root = (git -C $loopDir rev-parse --show-toplevel).Trim()
$jobsDir = Join-Path $loopDir 'reports/jobs'
New-Item -ItemType Directory -Force $jobsDir | Out-Null

$safe = ($Name -replace '[^A-Za-z0-9_.-]', '-')
$id = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $safe
$wslRoot = (wsl.exe -d $Distro -- wslpath -a $root).Trim()
$wslJobs = "$wslRoot/auto-loop/reports/jobs"

# LF line endings, no BOM, so bash reads the command as written.
[IO.File]::WriteAllText((Join-Path $jobsDir "$id.cmd"), ($Command -replace "`r`n", "`n") + "`n")

if (-not $NoSync) {
    $sync = "cd '$wslRoot' && rsync -a src scripts tests configs assets pyproject.toml ~/RL_Fall/"
    wsl.exe -d $Distro -- bash -lc $sync
    if ($LASTEXITCODE -ne 0) { throw "sync code to ~/RL_Fall failed (exit $LASTEXITCODE)" }
    $head = (git -C $root rev-parse --short HEAD).Trim()
    $dirty = if (git -C $root status --porcelain -- src scripts tests configs assets) { ' + uncommitted changes' } else { '' }
    Add-Content (Join-Path $jobsDir "$id.sync.txt") "synced from C:\RL_Fall $head$dirty at $(Get-Date -Format s)"
}

# A hidden wsl.exe that lives as long as the job keeps the WSL VM up after Claude exits.
$p = Start-Process wsl.exe -WindowStyle Hidden -PassThru -ArgumentList @(
    '-d', $Distro, '--', 'bash', "$wslRoot/auto-loop/tools/job-wrapper.sh", $id, $wslJobs)

Write-Host "job started: $id  (windows pid $($p.Id))"
Write-Host "log:    auto-loop/reports/jobs/$id.log"
Write-Host "status: auto-loop/reports/jobs/$id.json"
