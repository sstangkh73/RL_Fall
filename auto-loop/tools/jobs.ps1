<#
  แสดงสถานะ job ทั้งหมดที่รันผ่าน wsl-job.ps1 พร้อมเวลาที่ใช้
  ใช้:  pwsh -NoProfile -File auto-loop/tools/jobs.ps1 [-Running]
  สถานะ stale = ไม่มี heartbeat เกิน 10 นาที (job น่าจะตายไปโดยไม่ได้บันทึกการจบ)
#>
param([switch]$Running)
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture

function Get-LoopJobs {
    $jobsDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'reports/jobs'
    if (-not (Test-Path $jobsDir)) { return @() }
    $now = [DateTimeOffset]::Now.ToUnixTimeSeconds()
    foreach ($f in Get-ChildItem $jobsDir -Filter *.json | Sort-Object Name) {
        # ไฟล์อาจว่างหรือ JSON ไม่ครบชั่วขณะ เพราะ WSL กำลังเขียนทับด้วย printf >
        $j = try { Get-Content $f.FullName -Raw | ConvertFrom-Json } catch { $null }
        if (-not $j) { [pscustomobject]@{ Job = $f.BaseName; State = 'writing' }; continue }
        $start = [DateTimeOffset]::FromUnixTimeSeconds([long]$j.start_epoch).ToLocalTime()
        $state = $j.state
        if ($state -eq 'running') {
            $hb = Join-Path $jobsDir "$($j.id).heartbeat"
            # heartbeat ถูกเขียนทับทุก 60 วิ ถ้าอ่านเจอไฟล์ว่าง ให้ใช้เวลาแก้ไขไฟล์แทน
            $raw = if (Test-Path $hb) { try { Get-Content $hb -Raw -ErrorAction Stop } catch { $null } }
            $beat = if ("$raw".Trim() -match '^\d+$') { [long]$Matches[0] }
                elseif (Test-Path $hb) { ([DateTimeOffset](Get-Item $hb).LastWriteTime).ToUnixTimeSeconds() }
                else { $start.ToUnixTimeSeconds() }
            if ($now - $beat -gt 600) { $state = 'stale' }
            $secs = $now - $start.ToUnixTimeSeconds()
        } else { $secs = [long]$j.duration_s }
        [pscustomobject]@{
            Job = $j.id; State = $state; Start = $start.ToString('yyyy-MM-dd HH:mm')
            Elapsed = [TimeSpan]::FromSeconds($secs).ToString('d\.hh\:mm\:ss'); Hours = [math]::Round($secs / 3600, 2)
            Exit = $j.exit_code
        }
    }
}

$jobs = @(Get-LoopJobs)
if ($Running) { $jobs = @($jobs | Where-Object State -eq 'running') }
if ($jobs.Count -eq 0) { Write-Host 'no jobs'; exit 0 }
$jobs | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
