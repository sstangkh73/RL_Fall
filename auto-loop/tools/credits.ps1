<#
  แสดงโควตาที่ใช้ไปของ Claude และ Codex (window 5 ชม. และ 7 วัน) เป็นหลอด พร้อมเวลารีเซ็ต และค่าใช้จ่ายรวมของลูป
  ใช้:  pwsh -NoProfile -File auto-loop/tools/credits.ps1                  แสดงครั้งเดียว
        pwsh -NoProfile -File auto-loop/tools/credits.ps1 -Watch [-Interval 60]   หน้าจอดูสด อัปเดตทุก N วินาที (Ctrl+C ออก)
  เปิดหน้าต่างแยก:
        Start-Process pwsh '-NoProfile -File C:\RL_Fall\auto-loop\tools\credits.ps1 -Watch'

  ตัวเลขมาจาก quota.ps1 (ค่าสด ถามทุกนาทีโดยไม่เสีย token: Codex ผ่าน app-server, Claude ผ่าน /usage ชุดเดียวกับหน้าแอป)
  ถ้าถามสดไม่ได้จะใช้ค่าจาก log แล้วบอกว่าข้อมูลเก่ากี่นาที ใส่ -NoProbe เพื่ออ่านจาก cache/log อย่างเดียว
  บรรทัดล่างสุดคือตัวนำที่ลูปจะเลือกถ้าเริ่มรอบใหม่ตอนนี้
  หลอด: █ = โควตาที่ใช้ไป, ┃ = เวลาที่ผ่านไปของ window (ถ้า █ เลย ┃ แปลว่าใช้เร็วกว่าเวลา)
  ค่า $ ของ Claude คือราคาเทียบ API (total_cost_usd) ไม่ใช่เงินที่ถูกเก็บจริงถ้าใช้ subscription
#>
param([switch]$Watch, [int]$Interval = 60, [int]$Width = 40, [switch]$NoProbe)
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$LoopDir = Split-Path $PSScriptRoot -Parent
# dot-source จะเขียนทับพารามิเตอร์ชื่อเดียวกัน ($NoProbe) จึงเก็บค่าไว้ก่อน
$probeOff = [bool]$NoProbe
. (Join-Path $PSScriptRoot 'quota.ps1')
$script:Now = [DateTimeOffset]::Now

function When([long]$epoch) { [DateTimeOffset]::FromUnixTimeSeconds($epoch).ToLocalTime() }
function Fmt-Left([DateTimeOffset]$t) {
    $d = $t - $script:Now
    if ($d.TotalSeconds -le 0) { return 'รีเซ็ตแล้ว' }
    if ($d.TotalDays -ge 1) { return 'อีก {0} วัน {1} ชม.' -f [int][math]::Floor($d.TotalDays), $d.Hours }
    'อีก {0} ชม. {1} นาที' -f [int][math]::Floor($d.TotalHours), $d.Minutes
}
function Age([datetime]$t) {
    $m = [int]([DateTimeOffset]::Now.LocalDateTime - $t).TotalMinutes
    if ($m -lt 1) { 'เมื่อกี้' } elseif ($m -lt 60) { "$m นาทีก่อน" } else { '{0:N1} ชม.ก่อน' -f ($m / 60) }
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
    Show-Quota (Get-AgentQuota claude -NoProbe:$probeOff)
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
    $q = Get-AgentQuota codex -NoProbe:$probeOff
    Show-Quota $q
    if ($q -and $q.ResetCredits) {
        Write-Host ('  เครดิตรีเซ็ตฟรี (รีเซ็ตทั้งสัปดาห์ + 5 ชม.): {0} ใบ  — ลูปไม่ใช้เอง ใช้ได้จากแอป Codex' -f $q.ResetCredits) -ForegroundColor DarkCyan
    }
}

# หลอด 5 ชม. และสัปดาห์ของหนึ่งตัว จาก object ของ quota.ps1
function Show-Quota($q) {
    if (-not $q) { Write-Host '  ไม่มีข้อมูล (ถามสดไม่ได้และไม่พบใน log)' -ForegroundColor DarkGray; return }
    $src = if ($q.Source -eq 'live') { 'สด' } else { $q.Source }
    $plan = if ($q.Plan) { "  แผน: $($q.Plan)" } else { '' }
    Write-Host ('  ข้อมูล{0} ณ {1:HH:mm:ss} ({2}){3}' -f $src, (When $q.AsOf), (Age (When $q.AsOf).LocalDateTime), $plan) -ForegroundColor DarkGray
    Show-Bar '5 ชม.' $q.Used5 $q.Reset5 $q.Win5
    Show-Bar 'สัปดาห์' $q.UsedW $q.ResetW $q.WinW
    if ($q.Blocked) { Write-Host "  ถูกบล็อก: $($q.Blocked)" -ForegroundColor Red }
}

function Show-All {
    $script:Now = [DateTimeOffset]::Now
    Show-Claude
    Write-Host ''
    Show-Codex
    Write-Host ''
    $plan = Get-QuotaPlan -NoProbe
    if ($plan.Lead) {
        Write-Host ('  ▶ ตัวนำรอบหน้า: {0}  ตัวช่วย: {1}   ({2})' -f $plan.Lead, $(if ($plan.Helper) { $plan.Helper } else { 'ไม่มี' }), $plan.Why) -ForegroundColor Green
    } else {
        Write-Host ('  ▶ ลูปจะรอถึง {0:HH:mm}  ({1})' -f (When $plan.WaitUntil), $plan.Why) -ForegroundColor Yellow
    }
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
