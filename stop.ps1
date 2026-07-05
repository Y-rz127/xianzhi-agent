# stop.ps1 - 一键停止先知智能体
# 用法：.\stop.ps1             # 交互确认后停止
#       .\stop.ps1 -Force     # 跳过确认直接停止

param(
    [int]$Port = 8123,
    [switch]$Force
)

# 强制 UTF-8 输出（避免 PowerShell 误解析中文）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Continue"

# 收集所有需要终止的进程
$processesToKill = New-Object System.Collections.Generic.List[int]

# 1. 找占用端口的进程
$conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        $processesToKill.Add($c.OwningProcess) | Out-Null
    }
}

# 2. 虚拟环境里的所有 python 子进程（uvicorn reload、MCP、pyppeteer 等）
$pyExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $pyExe) {
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $pyExe } | ForEach-Object {
        $processesToKill.Add($_.Id) | Out-Null
    }
}

# 3. 偶发残留：uvicorn / chromium
foreach ($name in @("uvicorn", "chromium", "chrome")) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        $processesToKill.Add($_.Id) | Out-Null
    }
}

$processesToKill = $processesToKill | Sort-Object -Unique

if (-not $processesToKill -or $processesToKill.Count -eq 0) {
    Write-Host "[stop.ps1] Port $Port is free, nothing to stop." -ForegroundColor Gray
    return
}

Write-Host ("[stop.ps1] About to terminate " + $processesToKill.Count + " process(es):") -ForegroundColor Yellow
foreach ($proc in $processesToKill) {
    $p = Get-Process -Id $proc -ErrorAction SilentlyContinue
    if ($p) {
        Write-Host ("  PID=" + $p.Id + "  " + $p.ProcessName + "  " + $p.Path) -ForegroundColor Gray
    }
}

if (-not $Force) {
    $ans = Read-Host "Confirm terminate? (y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") {
        Write-Host "[stop.ps1] Cancelled." -ForegroundColor Gray
        return
    }
}

foreach ($procId in $processesToKill) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host ("  [KILLED] PID=" + $procId) -ForegroundColor Green
    } catch {
        Write-Host ("  [FAILED] PID=" + $procId + " " + $_.Exception.Message) -ForegroundColor Red
    }
}

# 确认端口释放
Start-Sleep 1
$still = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($still) {
    Write-Host ("[stop.ps1] WARNING: port " + $Port + " is still in use.") -ForegroundColor Red
} else {
    Write-Host ("[stop.ps1] Port " + $Port + " is now free.") -ForegroundColor Green
}
