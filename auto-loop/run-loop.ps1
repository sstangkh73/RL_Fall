<#
  Claude + Codex autonomous loop สำหรับงานวิจัย RL Fall

  ใช้:     pwsh -File auto-loop/run-loop.ps1 [-MaxIterations 0] [-MaxHours 0] [-MaxTurnsPerIteration 150]
           0 = ไม่จำกัด (ค่าเริ่มต้น) แต่ทุกรอบและทุก job ถูกจับเวลาและบันทึกไว้
  หยุด:    สร้างไฟล์ auto-loop/STOP (หยุดก่อนรอบถัดไปหรือระหว่างรอ job) หรือกด Ctrl+C

  หลักการ: ลูปนี้ (ไม่ใช่ Claude) ตัดสินว่าเสร็จหรือยัง โดยดูจาก verify.ps1 เท่านั้น
  Claude ทำงานที่ root ของโปรเจกต์ และลูป commit ทุกรอบลง branch $Branch
  งานยาว (เทรนใน WSL) ให้รันผ่าน tools/wsl-job.ps1 แล้วสร้างไฟล์ auto-loop/WAIT_FOR_JOBS
  ลูปจะรอจน job ทั้งหมดจบก่อนเรียก Claude รอบถัดไป (ไม่เปลือง token ระหว่างรอ)

  รายงาน (อัปเดตตลอด):
    auto-loop/reports/loop-report.md   ทุกรอบ: เวลา Claude, เวลารอ job, เวลา verify, ผล, commit
    auto-loop/reports/iterations.csv   ข้อมูลเดียวกันแบบตาราง
    auto-loop/reports/jobs.md          ทุก job ใน WSL: เริ่ม จบ ใช้เวลา exit
    auto-loop/reports/goal-status.md   สถานะ M1–M4 ล่าสุด
    auto-loop/reports/codex.md         ทุกครั้งที่สั่ง Codex: คำสั่งที่ส่ง, คำสั่งที่ Codex รัน, คำตอบ, เวลา
    auto-loop/.loop/iter-NNN.log       ทุกอย่างที่ Claude ทำในรอบนั้น (เห็นสดบนหน้าจอด้วย)
    auto-loop/.loop/iter-NNN.jsonl     event ดิบจาก claude --output-format stream-json
#>
param(
    [int]$MaxIterations = 0,
    [double]$MaxHours = 0,
    [int]$MaxTurnsPerIteration = 150,
    [string]$Branch = 'loop/research',
    [int]$WaitPollSeconds = 120
)

$ErrorActionPreference = 'Stop'
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
# claude/codex พิมพ์ UTF-8 ถ้าไม่ตั้ง ภาษาไทยและอักขระพิเศษจะเพี้ยน
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$LoopDir = $PSScriptRoot
$Root = (git -C $LoopDir rev-parse --show-toplevel).Trim()
Set-Location $Root

# เครื่องมือที่ Claude ใช้ได้โดยไม่ต้องขออนุญาต: แก้ไฟล์, ค้นเว็บ, WSL (เทรน/วิเคราะห์),
# job runner, Codex, python และ git แบบอ่าน
$AllowedTools = @(
    'Read', 'Edit', 'Write', 'Glob', 'Grep', 'WebSearch', 'WebFetch',
    'Bash(wsl.exe:*)', 'Bash(wsl:*)',
    'Bash(pwsh -NoProfile -File auto-loop/tools/wsl-job.ps1:*)',
    'Bash(pwsh -NoProfile -File auto-loop/tools/jobs.ps1:*)',
    'Bash(pwsh -NoProfile -File auto-loop/verify.ps1)',
    'Bash(bash auto-loop/tools/codex.sh:*)',
    'Bash(python:*)', 'Bash(nvidia-smi:*)',
    'Bash(git diff:*)', 'Bash(git status:*)', 'Bash(git log:*)', 'Bash(git show:*)'
)

# ไฟล์ที่ AI ห้ามแก้ ถ้าถูกแก้ลูปจะหยุดทันที (กันการโกงให้ verify ผ่าน)
$Protected = @('verify.ps1', 'GOAL.md', 'PROMPT.md', 'run-loop.ps1') +
    @(Get-ChildItem (Join-Path $LoopDir 'tools') -File | ForEach-Object { "tools/$($_.Name)" }) |
    ForEach-Object { "auto-loop/$_" }

# คำสั่ง Bash ของ Claude (รวม Codex) รันได้นานสุด 30 นาทีต่อครั้ง งานที่นานกว่านั้นต้องใช้ wsl-job.ps1
$env:BASH_DEFAULT_TIMEOUT_MS = '1800000'
$env:BASH_MAX_TIMEOUT_MS = '1800000'

foreach ($cmd in 'claude', 'codex', 'git', 'wsl.exe') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "ไม่พบคำสั่ง '$cmd' — ดูขั้นติดตั้งใน auto-loop/README.md"
    }
}

$current = (git branch --show-current).Trim()
if ($current -ne $Branch) {
    git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -eq 0) { git switch $Branch } else { git switch -c $Branch }
    if ($LASTEXITCODE -ne 0) { throw "สลับไป branch $Branch ไม่ได้" }
}

$Hashes = @{}
foreach ($f in $Protected) { $Hashes[$f] = (Get-FileHash $f).Hash }

$dotLoop = Join-Path $LoopDir '.loop'
$reports = Join-Path $LoopDir 'reports'
New-Item -ItemType Directory -Force $dotLoop, $reports | Out-Null
$ReportMd = Join-Path $reports 'loop-report.md'
$ReportCsv = Join-Path $reports 'iterations.csv'
$StopFile = Join-Path $LoopDir 'STOP'
$WaitFile = Join-Path $LoopDir 'WAIT_FOR_JOBS'

function Fmt([TimeSpan]$t) { '{0}:{1:mm}:{1:ss}' -f [int][math]::Floor($t.TotalHours), $t }
function Report([string]$line) { Add-Content -Path $ReportMd -Value $line -Encoding utf8 }

# --- แสดงสิ่งที่ Claude ทำแบบสด (จาก --output-format stream-json) ---
# หน้าจอและ .loop/iter-NNN.log ได้ข้อความอ่านง่าย ส่วน .loop/iter-NNN.jsonl เก็บ event ดิบทั้งหมด
$script:CodexCalls = @{}
$script:LastResult = $null

function Out-Live([string]$text, [string]$color = 'Gray') {
    Write-Host $text -ForegroundColor $color
    Add-Content -Path $script:LiveLog -Value $text -Encoding utf8
}

function Short([string]$s, [int]$max = 400) {
    if ($null -eq $s) { return '' }
    $s = $s.TrimEnd()
    if ($s.Length -le $max) { return $s }
    return $s.Substring(0, $max) + " …(+$($s.Length - $max) ตัวอักษร)"
}

function Get-ResultText($content) {
    if ($content -is [string]) { return $content }
    (@($content) | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"
}

function Show-StreamEvent([string]$line) {
    Add-Content -Path $script:RawLog -Value $line -Encoding utf8
    $e = try { $line | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    if ($null -eq $e) { if ($line.Trim()) { Out-Live $line 'DarkYellow' }; return }
    switch ($e.type) {
        'system' {
            if ($e.subtype -eq 'init') { Out-Live "[เริ่ม] model $($e.model)  cwd $($e.cwd)" 'DarkGray' }
        }
        'assistant' {
            foreach ($c in @($e.message.content)) {
                if ($c.type -eq 'text' -and $c.text.Trim()) {
                    Out-Live "`n[Claude] $($c.text.Trim())" 'White'
                } elseif ($c.type -eq 'tool_use') {
                    $in = $c.input
                    if ($c.name -eq 'Bash' -and $in.command -match 'codex\.sh') {
                        $script:CodexCalls[$c.id] = $true
                        Out-Live "`n[Claude → Codex] สั่ง:`n$($in.command)" 'Magenta'
                        continue
                    }
                    $what = switch ($c.name) {
                        'Bash' { $in.command }
                        { $_ -in 'Read', 'Write', 'Edit', 'NotebookEdit' } { $in.file_path }
                        { $_ -in 'Grep', 'Glob' } { "$($in.pattern)  $($in.path)" }
                        'WebSearch' { $in.query }
                        'WebFetch' { $in.url }
                        default { ($in | ConvertTo-Json -Compress -Depth 4) }
                    }
                    Out-Live ("▶ {0}: {1}" -f $c.name, (Short $what 600)) 'Cyan'
                }
            }
        }
        'user' {
            foreach ($c in @($e.message.content)) {
                if ($c.type -ne 'tool_result') { continue }
                $text = Get-ResultText $c.content
                if ($script:CodexCalls.ContainsKey($c.tool_use_id)) {
                    Out-Live "[Codex → Claude] ตอบ:`n$($text.TrimEnd())`n" 'Magenta'
                } else {
                    $mark = if ($c.is_error) { '  ✗' } else { '  ↳' }
                    Out-Live "$mark $(Short (($text -split "`n" | Select-Object -First 12) -join "`n     ") 800)" 'DarkGray'
                }
            }
        }
        'result' {
            $script:LastResult = $e
            Out-Live ("`n=== Claude จบรอบ ({0}): {1} turns, `${2:N2}, {3}" -f $e.subtype, $e.num_turns, $e.total_cost_usd,
                (Fmt ([TimeSpan]::FromMilliseconds($e.duration_ms)))) 'Green'
            if ($e.result) { Out-Live $e.result 'Green' }
        }
    }
}

function Invoke-Verify {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $out = & pwsh -NoProfile -File (Join-Path $LoopDir 'verify.ps1') 2>&1 | Out-String
    $code = $LASTEXITCODE
    $sw.Stop()
    "exit=$code  ($(Get-Date -Format s), $(Fmt $sw.Elapsed))`n$out" | Set-Content (Join-Path $dotLoop 'last-verify.txt') -Encoding utf8
    return @{ Code = $code; Time = $sw.Elapsed }
}

function Get-ActiveJobs {
    # job ที่ยัง running และมี heartbeat ไม่เกิน 10 นาที
    $dir = Join-Path $reports 'jobs'
    if (-not (Test-Path $dir)) { return @() }
    $now = [DateTimeOffset]::Now.ToUnixTimeSeconds()
    @(Get-ChildItem $dir -Filter *.json | ForEach-Object {
        $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
        if ($j.state -eq 'running') {
            $hb = Join-Path $dir "$($j.id).heartbeat"
            $beat = if (Test-Path $hb) { [long](Get-Content $hb -Raw).Trim() } else { [long]$j.start_epoch }
            if ($now - $beat -le 600) { $j.id }
        }
    })
}

function Wait-Jobs {
    # คืนเวลาที่รอ; หยุดรอถ้ามีไฟล์ STOP
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $active = @(Get-ActiveJobs)
        if ($active.Count -eq 0 -or (Test-Path $StopFile)) { break }
        Write-Host "  รอ job: $($active -join ', ')  (รอมาแล้ว $(Fmt $sw.Elapsed))"
        Start-Sleep -Seconds $WaitPollSeconds
    }
    Remove-Item $WaitFile -ErrorAction SilentlyContinue
    return $sw.Elapsed
}

$loopStart = Get-Date
$deadline = if ($MaxHours -gt 0) { $loopStart.AddHours($MaxHours) } else { [datetime]::MaxValue }
if (-not (Test-Path $ReportCsv)) {
    'iteration,start,claude_s,claude_exit,wait_jobs_s,verify_s,verify_exit,iteration_s,total_elapsed_s,commit' |
        Set-Content $ReportCsv -Encoding utf8
}
Report "`n## Loop เริ่ม $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  branch $Branch  HEAD $((git rev-parse --short HEAD).Trim())"
Report "MaxIterations=$(if ($MaxIterations) { $MaxIterations } else { 'ไม่จำกัด' })  MaxHours=$(if ($MaxHours) { $MaxHours } else { 'ไม่จำกัด' })`n"
Report '| รอบ | เริ่ม | Claude | turns | ค่าใช้จ่าย Claude | รอ job | verify | รวมรอบ | เวลาสะสม | ผล verify | commit |'
Report '|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|'

$exitCode = 1
$endReason = 'ครบจำนวนรอบแต่ verify ยังไม่ผ่าน'
try {
    $v = Invoke-Verify
    if ($v.Code -eq 0) { $endReason = 'verify ผ่านอยู่แล้ว — ไม่มีอะไรต้องทำ'; $exitCode = 0 }

    for ($i = 1; $exitCode -ne 0 -and ($MaxIterations -le 0 -or $i -le $MaxIterations); $i++) {
        if (Test-Path $StopFile) { $endReason = 'พบไฟล์ STOP'; $exitCode = 2; break }
        if ((Get-Date) -gt $deadline) { $endReason = 'ครบเวลาที่กำหนด'; $exitCode = 2; break }

        $iterStart = Get-Date
        Write-Host "`n=== รอบที่ $i   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')   (เวลาสะสม $(Fmt ($iterStart - $loopStart))) ===" -ForegroundColor Cyan
        $script:LiveLog = Join-Path $dotLoop ('iter-{0:D3}.log' -f $i)
        $script:RawLog = Join-Path $dotLoop ('iter-{0:D3}.jsonl' -f $i)
        $script:LastResult = $null
        $sw = [Diagnostics.Stopwatch]::StartNew()
        Get-Content (Join-Path $LoopDir 'PROMPT.md') -Raw |
            claude -p --output-format stream-json --verbose --permission-mode acceptEdits `
                --max-turns $MaxTurnsPerIteration --allowedTools @AllowedTools 2>&1 |
            ForEach-Object { Show-StreamEvent "$_" }
        $claudeExit = $LASTEXITCODE
        $turns = if ($script:LastResult) { $script:LastResult.num_turns } else { '?' }
        $cost = if ($script:LastResult) { '${0:N2}' -f $script:LastResult.total_cost_usd } else { '?' }
        $sw.Stop()
        $claudeTime = $sw.Elapsed

        foreach ($f in $Protected) {
            if (-not (Test-Path $f) -or (Get-FileHash $f).Hash -ne $Hashes[$f]) {
                $endReason = "ไฟล์ที่ห้ามแก้ถูกแก้: $f (ดูด้วย git diff)"
                throw $endReason
            }
        }

        git add -A
        git commit -qm "loop: iteration $i" --allow-empty
        $commit = (git rev-parse --short HEAD).Trim()

        $waitTime = [TimeSpan]::Zero
        if (Test-Path $WaitFile) { $waitTime = Wait-Jobs }

        $v = Invoke-Verify
        $iterTime = (Get-Date) - $iterStart
        $total = (Get-Date) - $loopStart
        $result = if ($v.Code -eq 0) { 'ผ่าน' } else { 'ไม่ผ่าน' }
        Report ("| {0} | {1:yyyy-MM-dd HH:mm} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} | {10} |" -f
            $i, $iterStart, (Fmt $claudeTime), $turns, $cost, (Fmt $waitTime), (Fmt $v.Time), (Fmt $iterTime), (Fmt $total), $result, $commit)
        Add-Content $ReportCsv -Encoding utf8 -Value ('{0},{1:s},{2:F0},{3},{4:F0},{5:F0},{6},{7:F0},{8:F0},{9}' -f
            $i, $iterStart, $claudeTime.TotalSeconds, $claudeExit, $waitTime.TotalSeconds, $v.Time.TotalSeconds,
            $v.Code, $iterTime.TotalSeconds, $total.TotalSeconds, $commit)
        Write-Host "verify exit=$($v.Code)   รอบนี้ $(Fmt $iterTime)   สะสม $(Fmt $total)"

        if ($v.Code -eq 0) { $endReason = "สำเร็จ — verify ผ่านในรอบที่ $i"; $exitCode = 0; break }
    }
}
finally {
    $total = (Get-Date) - $loopStart
    Report "`nLoop จบ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') — $endReason — ใช้เวลารวม $(Fmt $total)"
    Write-Host "$endReason   ใช้เวลารวม $(Fmt $total)" -ForegroundColor $(if ($exitCode -eq 0) { 'Green' } else { 'Yellow' })
}
exit $exitCode
