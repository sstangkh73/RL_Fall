<#
  อ่านโควตาสดของ Claude และ Codex แล้วตัดสินว่ารอบถัดไปใครเป็นตัวนำ (ทำงานหนัก) ใครเป็นตัวช่วย (รีวิว)
  ใช้:  pwsh -NoProfile -File auto-loop/tools/quota.ps1            สรุปแบบอ่านง่าย
        pwsh -NoProfile -File auto-loop/tools/quota.ps1 -Json      แผนเป็น JSON
        pwsh -NoProfile -File auto-loop/tools/quota.ps1 -Check codex   exit 0 = ใช้ได้, 3 = ใกล้เต็ม (codex.sh / claude.ps1 ใช้)
  หรือ dot-source (. auto-loop/tools/quota.ps1) แล้วเรียก Get-QuotaPlan / Get-AgentQuota / Format-QuotaPrompt

  แหล่งข้อมูลสด:
    Codex:  codex app-server → account/rateLimits/read  (ไม่เสีย token)
    Claude: claude -p --model haiku 1 turn ไม่มี tool แล้วอ่าน rate_limit_event (~$0.0006 ต่อครั้ง)
            โควตานี้ใช้ร่วมกับ session แบบ interactive จึงต้องถามสด ไม่ใช่อ่านจาก log ของลูป
  ผลถูก cache ไว้ที่ auto-loop/.loop/quota-cache.json (Claude 10 นาที, Codex 1 นาที) ถ้าถามสดไม่ได้จะใช้ค่าจาก log

  วิธีเลือกตัวนำ (คะแนนสูงกว่าเป็นตัวนำ):
    คะแนน = ความเร่งด่วน 5 ชม. × ตัวคูณรายสัปดาห์
    ความเร่งด่วน 5 ชม. = % ที่เหลือใน window 5 ชม. / ชั่วโมงที่เหลือถึงรีเซ็ต (อย่างน้อย 0.25)
        โควตาที่จะรีเซ็ตเร็ว ถ้าไม่ใช้ตอนนี้ก็เสียเปล่า เช่น เหลือ 80% เท่ากัน ตัวที่รีเซ็ตใน 20 นาทีได้ 240 ตัวที่อีก 4 ชม. ได้ 20
    ตัวคูณรายสัปดาห์: r = สัดส่วนโควตาสัปดาห์ที่เหลือ / สัดส่วนเวลาสัปดาห์ที่เหลือ
        r < 1 (ใช้เร็วกว่าเวลา) → r² (อย่างน้อย 0.05) ลงโทษแรงเพื่อไม่ให้โควตาสัปดาห์หมดก่อนรีเซ็ต
        r ≥ 1 (ใช้ช้ากว่าเวลา) → r (สูงสุด 2)
    ใช้ไม่ได้ถ้า 5 ชม. ≥ 90% หรือ สัปดาห์ ≥ 95% หรือถูกบล็อก ถ้าใช้ไม่ได้ทั้งคู่ → รอถึงเวลาที่ตัวแรกกลับมาใช้ได้
#>
param([switch]$Json, [ValidateSet('', 'claude', 'codex')][string]$Check = '', [switch]$NoProbe)

# เกณฑ์ใช้ไม่ได้ (%) ปรับได้ด้วย env QUOTA_LIMIT_5H / QUOTA_LIMIT_WEEK
$QuotaLimit5h = if ($env:QUOTA_LIMIT_5H) { [double]$env:QUOTA_LIMIT_5H } else { 90 }
$QuotaLimitWeek = if ($env:QUOTA_LIMIT_WEEK) { [double]$env:QUOTA_LIMIT_WEEK } else { 95 }
$QuotaLoopDir = Split-Path $PSScriptRoot -Parent
$QuotaCache = Join-Path $QuotaLoopDir '.loop/quota-cache.json'
$QuotaMaxAge = @{ claude = 600; codex = 60 }

function Get-NowEpoch { [DateTimeOffset]::Now.ToUnixTimeSeconds() }

function New-Quota($agent, $source, $asOf, $used5, $reset5, $win5, $usedW, $resetW, $winW) {
    [pscustomobject]@{
        Agent = $agent; Source = $source; AsOf = [long]$asOf
        Used5 = [double]$used5; Reset5 = [long]$reset5; Win5 = [long]$win5
        UsedW = [double]$usedW; ResetW = [long]$resetW; WinW = [long]$winW
        Blocked = $null; Plan = $null; ResetCredits = 0
    }
}

# ---------- Codex ----------
function Get-CodexQuotaLive {
    $cmd = Get-Command codex.cmd -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command codex -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if (-not $cmd) { return $null }
    $psi = [Diagnostics.ProcessStartInfo]::new($cmd.Source, 'app-server')
    $psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false; $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $p = [Diagnostics.Process]::Start($psi)
    try {
        $p.StandardInput.WriteLine('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"rl-fall-quota","version":"1"}}}')
        $p.StandardInput.WriteLine('{"jsonrpc":"2.0","method":"initialized"}')
        $p.StandardInput.WriteLine('{"jsonrpc":"2.0","id":2,"method":"account/rateLimits/read"}')
        $p.StandardInput.Flush()
        $deadline = [DateTime]::Now.AddSeconds(20)
        while ([DateTime]::Now -lt $deadline) {
            $task = $p.StandardOutput.ReadLineAsync()
            if (-not $task.Wait([math]::Max(100, ($deadline - [DateTime]::Now).TotalMilliseconds))) { break }
            $line = $task.Result
            if ($null -eq $line) { break }
            if ($line -notmatch '"id":2') { continue }
            $r = ($line | ConvertFrom-Json).result
            if (-not $r -or -not $r.rateLimits.primary) { return $null }
            $l = $r.rateLimits
            $q = New-Quota 'codex' 'live' (Get-NowEpoch) $l.primary.usedPercent $l.primary.resetsAt ($l.primary.windowDurationMins * 60) `
                $l.secondary.usedPercent $l.secondary.resetsAt ($l.secondary.windowDurationMins * 60)
            $q.Plan = $l.planType
            $q.Blocked = if ($l.rateLimitReachedType) { $l.rateLimitReachedType } elseif ($r.ordinaryUsageAllowed -eq $false) { 'not allowed' } else { $null }
            $q.ResetCredits = @($r.rateLimitResetCredits.credits | Where-Object status -eq 'available').Count
            return $q
        }
        return $null
    } finally {
        try { $p.Kill($true) } catch {}
        $p.Dispose()
    }
}

function Get-CodexQuotaFromLog {
    $home_ = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
    $sessions = Join-Path $home_ 'sessions'
    if (-not (Test-Path $sessions)) { return $null }
    foreach ($f in Get-ChildItem $sessions -Recurse -Filter 'rollout-*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 30) {
        $hits = @(Select-String -Path $f.FullName -Pattern '"rate_limits":\{"limit_id":"codex"')
        for ($i = $hits.Count - 1; $i -ge 0; $i--) {
            $l = ($hits[$i].Line | ConvertFrom-Json).payload.rate_limits
            if (-not $l -or -not $l.primary) { continue }
            $q = New-Quota 'codex' 'log' ([DateTimeOffset]$f.LastWriteTime).ToUnixTimeSeconds() $l.primary.used_percent $l.primary.resets_at `
                ($l.primary.window_minutes * 60) $l.secondary.used_percent $l.secondary.resets_at ($l.secondary.window_minutes * 60)
            $q.Plan = $l.plan_type; $q.Blocked = $l.rate_limit_reached_type
            return $q
        }
    }
    return $null
}

# ---------- Claude ----------
function ConvertFrom-ClaudeRateLimit($info, $source, $asOf) {
    $w = $info.unifiedWindows
    if (-not $w -or -not $w.five_hour) { return $null }
    $q = New-Quota 'claude' $source $asOf ($w.five_hour.utilization * 100) $w.five_hour.resetsAt 18000 `
        ($w.seven_day.utilization * 100) $w.seven_day.resetsAt 604800
    $q.Blocked = if ($info.status -and $info.status -ne 'allowed' -and $info.status -ne 'allowed_warning') { $info.status } else { $null }
    return $q
}

function Get-ClaudeQuotaLive {
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { return $null }
    $lines = 'ตอบคำเดียว: ok' | & claude -p --model haiku --max-turns 1 --output-format stream-json --verbose `
        --tools '' --strict-mcp-config --setting-sources '' 2>$null
    $hit = @($lines | Where-Object { $_ -match '"type":"rate_limit_event"' }) | Select-Object -Last 1
    if (-not $hit) { return $null }
    ConvertFrom-ClaudeRateLimit ($hit | ConvertFrom-Json).rate_limit_info 'live' (Get-NowEpoch)
}

function Get-ClaudeQuotaFromLog {
    # รอบของลูป (iter-*.jsonl) และงานที่ Codex สั่ง Claude (claude/*.jsonl)
    $files = @(Get-ChildItem (Join-Path $QuotaLoopDir '.loop') -Recurse -Filter '*.jsonl' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 10)
    foreach ($f in $files) {
        $hit = Select-String -Path $f.FullName -Pattern '"type":"rate_limit_event"' | Select-Object -Last 1
        if ($hit) { return ConvertFrom-ClaudeRateLimit ($hit.Line | ConvertFrom-Json).rate_limit_info 'log' ([DateTimeOffset]$f.LastWriteTime).ToUnixTimeSeconds() }
    }
    return $null
}

# ---------- cache + รวม ----------
function Read-QuotaCache {
    try { Get-Content $QuotaCache -Raw -ErrorAction Stop | ConvertFrom-Json } catch { $null }
}

function Get-AgentQuota([ValidateSet('claude', 'codex')][string]$Agent, [switch]$NoProbe, [switch]$Fresh) {
    $cache = Read-QuotaCache
    $c = if ($cache) { $cache.$Agent } else { $null }
    if (-not $Fresh -and $c -and $c.Source -eq 'live' -and ((Get-NowEpoch) - $c.AsOf) -lt $QuotaMaxAge[$Agent]) { return $c }
    $q = $null
    if (-not $NoProbe) {
        $q = try { if ($Agent -eq 'codex') { Get-CodexQuotaLive } else { Get-ClaudeQuotaLive } } catch { $null }
        if ($q) {
            $all = [ordered]@{}
            if ($cache) { foreach ($p in $cache.PSObject.Properties) { $all[$p.Name] = $p.Value } }
            $all[$Agent] = $q
            try { $all | ConvertTo-Json -Depth 4 | Set-Content $QuotaCache -Encoding utf8 } catch {}
            return $q
        }
    }
    # ถามสดไม่ได้ → ใช้ค่าที่ใหม่กว่าระหว่าง cache กับ log
    $log = if ($Agent -eq 'codex') { Get-CodexQuotaFromLog } else { Get-ClaudeQuotaFromLog }
    if ($c -and (-not $log -or $c.AsOf -ge $log.AsOf)) { $c.Source = 'cache'; return $c }
    return $log
}

# คะแนนและสถานะของหนึ่งตัว (ถ้า window รีเซ็ตแล้ว ถือว่าเริ่มใหม่ที่ 0%)
function Measure-Quota($q) {
    $now = Get-NowEpoch
    if (-not $q) { return [pscustomobject]@{ Agent = $null; Available = $false; Score = 0; Reason = 'ไม่มีข้อมูล'; AvailableAt = $now + 1800 } }
    $used5 = $q.Used5; $left5 = $q.Reset5 - $now
    if ($left5 -le 0) { $used5 = 0; $left5 = $q.Win5 }
    $usedW = $q.UsedW; $leftW = $q.ResetW - $now
    if ($leftW -le 0) { $usedW = 0; $leftW = $q.WinW }

    $urgency = (100 - $used5) / [math]::Max($left5 / 3600.0, 0.25)
    $ratio = ((100 - $usedW) / 100.0) / [math]::Max($leftW / [double]$q.WinW, 0.02)
    # ใช้เร็วกว่าเวลาโดนลงโทษแบบกำลังสอง: โควตาสัปดาห์ที่เหลือน้อยสำคัญกว่าโควตา 5 ชม. ที่จะรีเซ็ต
    $weekFactor = if ($ratio -lt 1) { [math]::Max(0.05, $ratio * $ratio) } else { [math]::Min(2.0, $ratio) }
    $reasons = @()
    if ($used5 -ge $QuotaLimit5h) { $reasons += ('5 ชม. ใช้ไป {0:N0}%' -f $used5) }
    if ($usedW -ge $QuotaLimitWeek) { $reasons += ('สัปดาห์ใช้ไป {0:N0}%' -f $usedW) }
    if ($q.Blocked) { $reasons += "ถูกบล็อก ($($q.Blocked))" }
    $availableAt = if ($usedW -ge $QuotaLimitWeek) { $now + $leftW } elseif ($reasons) { $now + $left5 } else { $now }
    [pscustomobject]@{
        Agent = $q.Agent; Available = ($reasons.Count -eq 0); Score = [math]::Round($urgency * $weekFactor, 1)
        Urgency = [math]::Round($urgency, 1); WeekFactor = [math]::Round($weekFactor, 2)
        Used5 = $used5; Left5Min = [int]($left5 / 60); UsedW = $usedW; LeftWHours = [math]::Round($leftW / 3600.0, 1)
        WeekTimePct = [math]::Round(100 * (1 - $leftW / [double]$q.WinW), 0)
        Reason = ($reasons -join ', '); AvailableAt = [long]$availableAt; Source = $q.Source; AsOf = $q.AsOf
        ResetCredits = $q.ResetCredits
    }
}

function Get-QuotaPlan([switch]$NoProbe) {
    $m = @{}
    foreach ($a in 'claude', 'codex') { $m[$a] = Measure-Quota (Get-AgentQuota $a -NoProbe:$NoProbe); $m[$a].Agent = $a }
    $ok = @($m.Values | Where-Object Available | Sort-Object Score -Descending)
    $lead = if ($ok.Count) { $ok[0].Agent } else { $null }
    $helper = if ($ok.Count -gt 1) { $ok[1].Agent } else { $null }
    $waitUntil = if ($lead) { $null } else { ($m.Values | Measure-Object AvailableAt -Minimum).Minimum }
    $why = if (-not $lead) { 'ใช้ไม่ได้ทั้งคู่: ' + (($m.Values | ForEach-Object { "$($_.Agent) $($_.Reason)" }) -join '; ') }
        elseif (-not $helper) { "$lead เป็นตัวนำ (อีกตัวใช้ไม่ได้: $(($m.Values | Where-Object { -not $_.Available }).Reason))" }
        else { '{0} คะแนน {1} > {2} คะแนน {3}' -f $lead, $m[$lead].Score, $helper, $m[$helper].Score }
    [pscustomobject]@{ Lead = $lead; Helper = $helper; WaitUntil = $waitUntil; Why = $why; Claude = $m.claude; Codex = $m.codex; At = (Get-NowEpoch) }
}

function Format-QuotaRow($x) {
    $st = if ($x.Available) { 'ใช้ได้' } else { "ใกล้เต็ม: $($x.Reason)" }
    '| {0} | {1:N0}% (รีเซ็ตใน {2} นาที) | {3:N0}% (เวลาผ่านไป {4}%, รีเซ็ตใน {5} ชม.) | {6} | {7} |' -f
        $x.Agent, $x.Used5, $x.Left5Min, $x.UsedW, $x.WeekTimePct, $x.LeftWHours, $x.Score, $st
}

# ส่วนที่ลูปต่อท้าย PROMPT.md ทุกรอบ
function Format-QuotaPrompt($plan) {
    $helperLine = if ($plan.Helper) {
        if ($plan.Helper -eq 'codex') { 'ตัวช่วยรอบนี้คือ **Codex**: `bash auto-loop/tools/codex.sh "<คำสั่งงาน>"`' }
        else { 'ตัวช่วยรอบนี้คือ **Claude**: เขียนคำสั่งงานลงไฟล์ใน `tmp/` แล้วเรียก `pwsh -NoProfile -File auto-loop/tools/claude.ps1 -TaskFile tmp/<ไฟล์>.md`' }
    } else { 'รอบนี้ **ไม่มีตัวช่วย** (อีกตัวโควตาใกล้เต็ม) ทำเองทั้งหมด รีวิวงานตัวเองด้วย `git diff` ให้ละเอียดขึ้น' }
    $leadName = if ($plan.Lead -eq 'claude') { 'Claude' } else { 'Codex' }
    @"

## โควตาและบทบาทรอบนี้ (ลูปเขียนให้อัตโนมัติ)

คุณคือ **$leadName** และเป็น **ตัวนำ** รอบนี้ เพราะโควตาเหลือคุ้มกว่า ($($plan.Why))
$helperLine

| ตัว | 5 ชม. ใช้ไป | สัปดาห์ใช้ไป | คะแนน | สถานะ |
|---|---|---|---:|---|
$(Format-QuotaRow $plan.Claude)
$(Format-QuotaRow $plan.Codex)

- งานที่กิน token มาก (อ่านเอกสาร/log/โค้ดจำนวนมาก, เขียนโค้ดยาว, วิเคราะห์ผลหลายไฟล์) **ตัวนำทำเอง**
- ตัวช่วยใช้กับงานสั้น: รีวิว diff, ความเห็นที่สอง, ตรวจข้อสรุป ส่งเฉพาะข้อมูลที่จำเป็น อย่าสั่งให้อ่านทั้งโปรเจกต์
- ถ้าตัวช่วยตอบขึ้นต้นด้วย ``QUOTA:`` แปลว่าโควตามันใกล้เต็มแล้ว ให้ทำต่อเองโดยไม่ต้องเรียกซ้ำ
- บันทึกใน progress.md ด้วยว่ารอบนี้ใครเป็นตัวนำ
"@
}

function Show-QuotaPlan($plan) {
    foreach ($x in $plan.Claude, $plan.Codex) {
        $src = if ($x.Source -eq 'live') { 'สด' } else { "$($x.Source) $([int](((Get-NowEpoch) - $x.AsOf) / 60)) นาทีก่อน" }
        Write-Host ('  {0,-6} 5ชม. {1,3:N0}% (รีเซ็ต {2} นาที)  สัปดาห์ {3,3:N0}% (เวลา {4}%)  คะแนน {5,6}  {6}  [{7}]' -f
            $x.Agent, $x.Used5, $x.Left5Min, $x.UsedW, $x.WeekTimePct, $x.Score,
            $(if ($x.Available) { 'ใช้ได้' } else { "ใกล้เต็ม: $($x.Reason)" }), $src)
    }
    if ($plan.Lead) { Write-Host "  → ตัวนำ: $($plan.Lead)   ตัวช่วย: $(if ($plan.Helper) { $plan.Helper } else { 'ไม่มี' })" -ForegroundColor Green }
    else { Write-Host ("  → รอถึง {0:HH:mm}  ({1})" -f [DateTimeOffset]::FromUnixTimeSeconds($plan.WaitUntil).ToLocalTime(), $plan.Why) -ForegroundColor Yellow }
}

# ---------- เรียกเป็นสคริปต์ ----------
if ($MyInvocation.InvocationName -ne '.') {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    # locale ไทยจะได้ปี พ.ศ.
    [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
    if ($Check) {
        $x = Measure-Quota (Get-AgentQuota $Check -NoProbe:$NoProbe)
        if ($x.Available) { exit 0 }
        Write-Output ("QUOTA: {0} โควตาใกล้เต็ม ({1}) ใช้ได้อีกครั้ง {2:yyyy-MM-dd HH:mm} — ทำงานนี้เองแทน ไม่ต้องเรียกซ้ำ" -f
            $Check, $x.Reason, [DateTimeOffset]::FromUnixTimeSeconds($x.AvailableAt).ToLocalTime())
        exit 3
    }
    $plan = Get-QuotaPlan -NoProbe:$NoProbe
    if ($Json) { $plan | ConvertTo-Json -Depth 4 } else { Show-QuotaPlan $plan }
}
