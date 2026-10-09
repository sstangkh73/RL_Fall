<#
  แสดงโควตาที่ใช้ไปของ Claude และ Codex (window 5 ชม. และ 7 วัน) เป็นหลอด พร้อมเวลารีเซ็ต และค่าใช้จ่ายรวมของลูป
  ใช้:  pwsh -NoProfile -File auto-loop/tools/credits.ps1                  แสดงครั้งเดียว
        pwsh -NoProfile -File auto-loop/tools/credits.ps1 -Watch [-Interval 60]   หน้าจอดูสด อัปเดตทุก N วินาที (Ctrl+C ออก)
  เปิดหน้าต่างแยก:
        Start-Process pwsh '-NoProfile -File C:\RL_Fall\auto-loop\tools\credits.ps1 -Watch'

  อ่านจาก log อย่างเดียว ไม่เรียก API (ไม่เสียโควตา) ตัวเลขจึงเป็นค่า ณ การเรียกครั้งล่าสุด
    Claude: rate_limit_event ล่าสุดใน auto-loop/.loop/iter-*.jsonl (stream-json ของ claude -p)
    Codex:  rate_limits ล่าสุดใน ~/.codex/sessions/**/rollout-*.jsonl
  หลอด: █ = โควตาที่ใช้ไป, ┃ = เวลาที่ผ่านไปของ window (ถ้า █ เลย ┃ แปลว่าใช้เร็วกว่าเวลา)
  ค่า $ ของ Claude คือราคาเทียบ API (total_cost_usd) ไม่ใช่เงินที่ถูกเก็บจริงถ้าใช้ subscription
#>
param([switch]$Watch, [int]$Interval = 60, [int]$Width = 40)
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$LoopDir = Split-Path $PSScriptRoot -Parent
$script:Now = [DateTimeOffset]::Now

function When([long]$epoch) { [DateTimeOffset]::FromUnixTimeSeconds($epoch).ToLocalTime() }
function Fmt-Left([DateTimeOffset]$t) {
    $d = $t - $script:Now
    if ($d.TotalSeconds -le 0) { return 'รีเซ็ตแล้ว' }
    if ($d.TotalDays -ge 1) { return 'อีก {0} วัน {1} ชม.' -f [int][math]::Floor($d.TotalDays), $d.Hours }
    'อีก {0} ชม. {1} นาที' -f [int][math]::Floor($d.TotalHours), $d.Minutes
}
function Age([datetime]$t) {
    $m = [int]($script:Now.LocalDateTime - $t).TotalMinutes
    if ($m -lt 60) { "$m นาทีก่อน" } else { '{0:N1} ชม.ก่อน' -f ($m / 60) }
}

# หลอดหนึ่ง window: ชื่อ, % ที่ใช้, เวลารีเซ็ต (epoch), ความยาว window (วินาที)
# ถ้ารีเซ็ตไปแล้วหลังข้อมูลล่าสุด ตัวเลขเดิมไม่มีความหมาย แสดงเป็น 0%
function Show-Bar([string]$name, [double]$pct, [long]$resets, [long]$windowSec) {
    $t = When $resets
    if ($t -le $script:Now) { $pct = 0; $elapsed = 0 }
    else { $elapsed = [math]::Max(0.0, 1 - ($t - $script:Now).TotalSeconds / $windowSec) }
    $pct = [math]::Min([math]::Max($pct, 0.0), 100.0)
    $color = if ($pct -ge 90) { 'Red' } elseif ($pct -ge 70) { 'Yellow' } else { 'Green' }
    $fill = [int][math]::Round($pct / 100 * $Width)
    $mark = [math]::Min($Width - 1, [int][math]::Floor($elapsed * $Width))

    Write-Host ('  {0,-7} ' -f $name) -NoNewline
    for ($i = 0; $i -lt $Width; $i++) {
        if ($i -eq $mark -and $t -gt $script:Now) {
            $c = if ($i -lt $fill) { $color } else { 'White' }
            Write-Host '┃' -NoNewline -ForegroundColor $c
        } elseif ($i -lt $fill) { Write-Host '█' -NoNewline -ForegroundColor $color }
        else { Write-Host '░' -NoNewline -ForegroundColor DarkGray }
    }
    Write-Host (' {0,5:N1}%' -f $pct) -ForegroundColor $color
    Write-Host ('          รีเซ็ต {0} ({1})  เวลาผ่านไป {2:N0}%' -f $t.ToString('ddd dd/MM HH:mm'), (Fmt-Left $t), ($elapsed * 100)) -ForegroundColor DarkGray
}

function Show-Claude {
    Write-Host '━━ Claude ━━' -ForegroundColor Cyan
    $iterFiles = @(Get-ChildItem (Join-Path $LoopDir '.loop') -Filter 'iter-*.jsonl' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    $rl = $null; $rlFile = $null
    foreach ($f in $iterFiles) {
        $line = Select-String -Path $f.FullName -Pattern '"type":"rate_limit_event"' | Select-Object -Last 1
        if ($line) { $rl = ($line.Line | ConvertFrom-Json).rate_limit_info; $rlFile = $f; break }
    }
    if ($rl) {
        Write-Host ('  ข้อมูลจาก {0} ({1})' -f $rlFile.Name, (Age $rlFile.LastWriteTime)) -ForegroundColor DarkGray
        $w = $rl.unifiedWindows
        if ($w.five_hour) { Show-Bar '5 ชม.' ($w.five_hour.utilization * 100) $w.five_hour.resetsAt 18000 }
        if ($w.seven_day) { Show-Bar 'สัปดาห์' ($w.seven_day.utilization * 100) $w.seven_day.resetsAt 604800 }
        if ($rl.status -ne 'allowed') { Write-Host "  สถานะ: $($rl.status)" -ForegroundColor Red }
        if ($rl.isUsingOverage) { Write-Host '  กำลังใช้ overage' -ForegroundColor Yellow }
    } else {
        Write-Host '  ยังไม่มี rate_limit_event ใน auto-loop/.loop/iter-*.jsonl' -ForegroundColor DarkGray
    }
    # ค่าใช้จ่ายเทียบ API: รวม total_cost_usd จาก event result ของทุกรอบ
    $costs = foreach ($f in $iterFiles) {
        $r = Select-String -Path $f.FullName -Pattern '"type":"result"' | Select-Object -Last 1
        if ($r) { [pscustomobject]@{ Time = $f.LastWriteTime; Cost = [double]($r.Line | ConvertFrom-Json).total_cost_usd } }
    }
    if ($costs) {
        $today = ($costs | Where-Object { $_.Time.Date -eq $script:Now.LocalDateTime.Date } | Measure-Object Cost -Sum).Sum
        $all = ($costs | Measure-Object Cost -Sum)
        Write-Host ('  ค่าใช้จ่ายเทียบ API: วันนี้ ${0:N2} | รวม {1} รอบที่มี log ${2:N2}' -f [double]$today, $all.Count, $all.Sum)
    }
}

function Show-Codex {
    Write-Host '━━ Codex ━━' -ForegroundColor Cyan
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
    $sessions = Join-Path $codexHome 'sessions'
    $cx = $null; $cxFile = $null
    if (Test-Path $sessions) {
        # ไล่จากไฟล์ใหม่สุด หา rate_limits ที่มีตัวเลขจริง (primary ไม่เป็น null)
        foreach ($f in Get-ChildItem $sessions -Recurse -Filter 'rollout-*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 30) {
            $hits = @(Select-String -Path $f.FullName -Pattern '"rate_limits":\{"limit_id":"codex"')
            for ($i = $hits.Count - 1; $i -ge 0 -and -not $cx; $i--) {
                $r = ($hits[$i].Line | ConvertFrom-Json).payload.rate_limits
                if ($r -and $r.primary) { $cx = $r; $cxFile = $f }
            }
            if ($cx) { break }
        }
    }
    if (-not $cx) { Write-Host "  ไม่พบ rate_limits ใน $sessions" -ForegroundColor DarkGray; return }
    Write-Host ('  ข้อมูลจาก session {0} ({1})  แผน: {2}' -f $cxFile.Name.Substring(8, 19), (Age $cxFile.LastWriteTime), $cx.plan_type) -ForegroundColor DarkGray
    foreach ($p in @($cx.primary, $cx.secondary)) {
        if (-not $p) { continue }
        $name = if ($p.window_minutes -le 300) { '{0} ชม.' -f ($p.window_minutes / 60) } else { 'สัปดาห์' }
        Show-Bar $name $p.used_percent $p.resets_at ($p.window_minutes * 60)
    }
    $c = $cx.credits
    if ($c -and ($c.has_credits -or $c.unlimited)) {
        Write-Host ('  เครดิตเสริม: {0}' -f $(if ($c.unlimited) { 'ไม่จำกัด' } else { $c.balance }))
    }
    if ($cx.rate_limit_reached_type) { Write-Host "  ติด limit: $($cx.rate_limit_reached_type)" -ForegroundColor Red }
}

function Show-All {
    $script:Now = [DateTimeOffset]::Now
    Show-Claude
    Write-Host ''
    Show-Codex
    Write-Host ''
    Write-Host '  █ ใช้ไป   ┃ เวลาที่ผ่านไปของ window (█ เลย ┃ = ใช้เร็วกว่าเวลา)' -ForegroundColor DarkGray
}

if (-not $Watch) { Write-Host ''; Show-All; Write-Host ''; return }

$Host.UI.RawUI.WindowTitle = 'เครดิต Claude / Codex'
while ($true) {
    Clear-Host
    Write-Host ("  เครดิต Claude / Codex   {0}   (อัปเดตทุก {1} วิ, Ctrl+C ออก)`n" -f (Get-Date -Format 'HH:mm:ss'), $Interval) -ForegroundColor White
    Show-All
    Start-Sleep -Seconds $Interval
}
