# ==============================================================================
# PMS 四门禁 CI 脚本（PowerShell，Windows 5.1+ 兼容）
#
# 门禁顺序（按依赖排序）：
#   1. 后端测试     : pytest -q -W ignore::pytest.PytestUnhandledThreadExceptionWarning
#   2. 迁移零漂移   : alembic upgrade head + alembic check（临时库 _alembic_check.db）
#   3. 前端类型     : tsc --noEmit
#   4. 前端构建     : vite build
#
# 行为：
#   - 任一步失败 => 立即停止后续门禁，打印醒目失败信息，输出汇总表后以非 0 退出
#   - 每步打印耗时（秒）
#   - 结尾汇总四门禁 PASS/FAIL 表
#   - 可从任意目录调用，项目根由 $PSScriptRoot 解析
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\scripts\ci.ps1
# ==============================================================================

#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

# ---------------------------------------------------------------- 路径解析 ---
$ScriptDir    = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$ProjectRoot  = Split-Path -Parent $ScriptDir
$Python       = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $Python) { throw "未找到 Python 解释器，也未找到 $ProjectRoot\.venv\Scripts\python.exe" }
}
$TempDb       = '_alembic_check.db'
# 日志目录放在项目内（已被 .gitignore 排除），失败后保留供排查。
$LogDir       = Join-Path $ProjectRoot '.ci-logs'
if (Test-Path $LogDir) { Remove-Item -Recurse -Force $LogDir -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$GateStatus = @('SKIP', 'SKIP', 'SKIP', 'SKIP')
$GateTime   = @('-', '-', '-', '-')
$GateTotalStart = Get-Date
$Failed = $false

# ------------------------------------------------------------------ 工具函数 ---
function Write-Hr {
    Write-Host ('=' * 78)
}

function Write-Banner {
    param([string]$Text)
    Write-Host ''
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Text" -ForegroundColor Cyan
}

function Remove-TempDb {
    foreach ($f in @($TempDb, "$TempDb-shm", "$TempDb-wal")) {
        $p = Join-Path $ProjectRoot $f
        if (Test-Path $p) { Remove-Item -Force $p -ErrorAction SilentlyContinue }
    }
}

function Write-GateLogTail {
    param([string]$Path, [int]$Lines = 8)
    if (Test-Path $Path) {
        Get-Content $Path -Tail $Lines | ForEach-Object { Write-Host "     | $_" }
    }
}

# ------------------------------------------------------------- 门禁执行器 ---
# Invoke-Gate <序号> <名称> <可执行文件> <参数数组>
function Invoke-Gate {
    param(
        [int]$Index,
        [string]$Name,
        [string]$Exe,
        [string[]]$Arguments
    )

    $log = Join-Path $LogDir "gate$Index.log"
    $start = Get-Date
    Write-Banner "[$Index/4] $Name 开始..."

    $output = & $Exe @Arguments 2>&1
    $code = $LASTEXITCODE
    $output | Set-Content -Path $log -Encoding UTF8

    $dur = [int]((Get-Date) - $start).TotalSeconds

    if ($code -eq 0) {
        $script:GateStatus[$Index - 1] = 'PASS'
        $script:GateTime[$Index - 1]   = "$dur"
        Write-Host "  PASS  $Name （耗时 ${dur}s，输出末尾 8 行）" -ForegroundColor Green
        Write-GateLogTail -Path $log -Lines 8
        return $true
    }

    $script:GateStatus[$Index - 1] = 'FAIL'
    $script:GateTime[$Index - 1]   = "$dur"
    Write-Host ''
    Write-Hr
    Write-Host "门禁失败：$Name（耗时 ${dur}s）" -ForegroundColor Red
    Write-Hr
    Write-Host "—— 命令：$Exe $($Arguments -join ' ')" -ForegroundColor Yellow
    Write-Host "—— 输出末尾 60 行：" -ForegroundColor Yellow
    Write-GateLogTail -Path $log -Lines 60
    Write-Hr
    $script:Failed = $true
    return $false
}

function Write-Summary {
    $total = [int]((Get-Date) - $GateTotalStart).TotalSeconds
    Write-Host ''
    Write-Hr
    Write-Host '                        PMS 四门禁汇总'
    Write-Hr
    Write-Host ('{0,-4} {1,-28} {2,-8} {3}' -f '#', '门禁', '结果', '耗时')
    Write-Host ('{0,-4} {1,-28} {2,-8} {3}' -f '----', '----------------------------', '--------', '--------')

    $names = @('后端测试 pytest', '迁移零漂移 alembic check', '前端类型 tsc --noEmit', '前端构建 vite build')
    for ($i = 0; $i -lt 4; $i++) {
        $st = $GateStatus[$i]
        $tm = $GateTime[$i]
        if ($tm -ne '-') { $tm = "${tm}s" }
        $line = '{0,-4} {1,-28} {2,-8} {3}' -f ($i + 1), $names[$i], $st, $tm
        switch ($st) {
            'PASS' { Write-Host $line -ForegroundColor Green }
            'FAIL' { Write-Host $line -ForegroundColor Red }
            default { Write-Host $line -ForegroundColor Yellow }
        }
    }

    Write-Hr
    if (-not $Failed) {
        Write-Host "全部四门禁通过（总耗时 ${total}s）" -ForegroundColor Green
    }
    else {
        Write-Host "CI 失败：存在未通过的门禁（总耗时 ${total}s）" -ForegroundColor Red
    }
    Write-Hr
}

function Complete-Ci {
    Write-Summary
    # 清理临时迁移检查库；日志目录 .ci-logs/ 保留供失败排查
    Remove-TempDb
    Remove-Item Env:\PMS_DATABASE_URL -ErrorAction SilentlyContinue
    if ($Failed) { exit 1 }
    exit 0
}

# =============================================================== 门禁 1/4 ===
Set-Location $ProjectRoot
Write-Hr
Write-Host "PMS CI 启动（项目根：$ProjectRoot）"
Write-Hr

# 注意：-W ignore::pytest.PytestUnhandledThreadExceptionWarning 是必须的。
# asyncio 拆卸期抛出的该警告会把 pytest 退出码抬升为 1，造成“假失败”。
$ok = Invoke-Gate -Index 1 -Name '后端测试 pytest' -Exe $Python -Arguments @(
    '-m', 'pytest', '-q', '-W', 'ignore::pytest.PytestUnhandledThreadExceptionWarning'
)
if (-not $ok) { Complete-Ci }

# =============================================================== 门禁 2/4 ===
$start = Get-Date
Write-Banner '[2/4] 迁移零漂移 alembic check 开始...'
Remove-TempDb

$env:PMS_DATABASE_URL = "sqlite+aiosqlite:///./$TempDb"
$upgradeLog = Join-Path $LogDir 'gate2_upgrade.log'
$checkLog   = Join-Path $LogDir 'gate2_check.log'

& $Python -m alembic upgrade head 2>&1 | Set-Content -Path $upgradeLog -Encoding UTF8
$upgradeOk = ($LASTEXITCODE -eq 0)

$checkOk = $false
if ($upgradeOk) {
    & $Python -m alembic check 2>&1 | Set-Content -Path $checkLog -Encoding UTF8
    if ($LASTEXITCODE -eq 0) {
        $checkOk = (Select-String -Path $checkLog -Pattern 'No new upgrade operations detected' -Quiet)
    }
    else {
        Write-Host 'alembic check 命令返回非 0' -ForegroundColor Yellow
    }
}
else {
    Write-Host 'alembic upgrade head 失败' -ForegroundColor Yellow
}

Remove-TempDb
Remove-Item Env:\PMS_DATABASE_URL -ErrorAction SilentlyContinue

$dur = [int]((Get-Date) - $start).TotalSeconds
if ($checkOk) {
    $GateStatus[1] = 'PASS'
    $GateTime[1]   = "$dur"
    Write-Host "  PASS  迁移零漂移 alembic check（耗时 ${dur}s）" -ForegroundColor Green
    Select-String -Path $checkLog -Pattern 'No new upgrade operations detected' | ForEach-Object { Write-Host "     | $($_.Line.Trim())" }
}
else {
    $GateStatus[1] = 'FAIL'
    $GateTime[1]   = "$dur"
    Write-Host ''
    Write-Hr
    Write-Host "门禁失败：迁移零漂移 alembic check（耗时 ${dur}s）" -ForegroundColor Red
    Write-Hr
    Write-Host '—— alembic upgrade head 输出末尾 30 行：' -ForegroundColor Yellow
    Write-GateLogTail -Path $upgradeLog -Lines 30
    Write-Host '—— alembic check 输出末尾 30 行：' -ForegroundColor Yellow
    Write-GateLogTail -Path $checkLog -Lines 30
    Write-Hr
    $Failed = $true
    Complete-Ci
}

# =============================================================== 门禁 3/4 ===
Set-Location (Join-Path $ProjectRoot 'web')
$ok = Invoke-Gate -Index 3 -Name '前端类型 tsc --noEmit' -Exe '.\node_modules\.bin\tsc.cmd' -Arguments @('--noEmit')
if (-not $ok) { Complete-Ci }

# =============================================================== 门禁 4/4 ===
Set-Location (Join-Path $ProjectRoot 'web')
$ok = Invoke-Gate -Index 4 -Name '前端构建 vite build' -Exe '.\node_modules\.bin\vite.cmd' -Arguments @('build')
if (-not $ok) { Complete-Ci }

Set-Location $ProjectRoot
Complete-Ci
