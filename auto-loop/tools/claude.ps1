<#
  ให้ Codex (ตอนเป็นตัวนำ) ส่งงานสั้นให้ Claude ทำแบบไม่ถามกลับ เช่น รีวิว diff หรือขอความเห็นที่สอง
  แล้วพิมพ์คำตอบสุดท้ายของ Claude พร้อมเวลาที่ใช้ (คู่กับ codex.sh ที่ Claude ใช้เรียก Codex)
  ใช้:  pwsh -NoProfile -File auto-loop/tools/claude.ps1 -TaskFile tmp/task.md   (แนะนำ: เลี่ยงปัญหา quote)
        pwsh -NoProfile -File auto-loop/tools/claude.ps1 -Task "คำสั่งงาน"
  ถ้าโควตา Claude ใกล้เต็ม จะไม่เรียก แต่พิมพ์ข้อความขึ้นต้นด้วย QUOTA: แล้ว exit 3
  บันทึก: auto-loop/reports/claude-helper.md (สั่งอะไร ตอบอะไร) และ auto-loop/.loop/claude/<ts>.jsonl (event ดิบ)
#>
param([string]$Task = '', [string]$TaskFile = '', [int]$MaxTurns = 40)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture

if ($TaskFile) { $Task = Get-Content $TaskFile -Raw -Encoding utf8 }
if (-not $Task.Trim()) { Write-Error 'usage: claude.ps1 -TaskFile <file> | -Task "<task>"'; exit 2 }

$root = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
Set-Location $root

$msg = & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'quota.ps1') -Check claude
if ($LASTEXITCODE -eq 3) { Write-Output $msg; exit 3 }

$dir = Join-Path $root 'auto-loop/.loop/claude'
New-Item -ItemType Directory -Force $dir | Out-Null
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$raw = Join-Path $dir "$ts.jsonl"

# Claude ตอนเป็นตัวช่วย: อ่าน/แก้ไฟล์, ค้นเว็บ, git แบบอ่าน, WSL, python ได้ แต่เรียก Codex หรือสั่ง job ไม่ได้
$allowed = @(
    'Read', 'Edit', 'Write', 'Glob', 'Grep', 'WebSearch', 'WebFetch',
    'Bash(wsl.exe:*)', 'Bash(wsl:*)', 'Bash(python:*)',
    'Bash(git diff:*)', 'Bash(git status:*)', 'Bash(git log:*)', 'Bash(git show:*)'
)
$sw = [Diagnostics.Stopwatch]::StartNew()
$Task | & claude -p --output-format stream-json --verbose --permission-mode acceptEdits `
    --max-turns $MaxTurns --allowedTools @allowed 2>&1 | ForEach-Object { "$_" } | Set-Content $raw -Encoding utf8
$code = $LASTEXITCODE
$sw.Stop()

# ลำดับ key ใน event ไม่แน่นอน จึง parse แล้วดู .type
$result = Get-Content $raw -Encoding utf8 | Where-Object { $_ -match '"type":"result"' } |
    ForEach-Object { try { $_ | ConvertFrom-Json } catch {} } | Where-Object type -eq 'result' | Select-Object -Last 1
$reply = if ($result.result) { $result.result } else { (Get-Content $raw -Tail 40 -Encoding utf8) -join "`n" }
$cost = if ($result) { '${0:N2}, {1} turns' -f $result.total_cost_usd, $result.num_turns } else { '?' }
$dur = [int]$sw.Elapsed.TotalSeconds

$report = Join-Path $root 'auto-loop/reports/claude-helper.md'
if (-not (Test-Path $report)) {
    "# Claude helper calls`n`nทุกครั้งที่ Codex ในลูปสั่งงาน Claude ผ่าน tools/claude.ps1" | Set-Content $report -Encoding utf8
}
@"

## $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  (exit $code, ${dur}s, $cost)

**Codex สั่ง:**

````text
$Task
````

**Claude ตอบ:**

$reply

event ดิบ: ``auto-loop/.loop/claude/$ts.jsonl``
"@ | Add-Content $report -Encoding utf8

Write-Output "[claude exit=$code | ${dur}s | $cost | raw: $raw]"
Write-Output $reply
exit $code
