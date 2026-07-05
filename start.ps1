# start.ps1 - 一键启动先知智能体
# 用法：.\start.ps1               # Foreground (Ctrl+C to stop)
#       .\start.ps1 -Background   # Background (silent, returns immediately)

param(
    [switch]$Background
)

# 强制 UTF-8 输出
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$port = 8123

# 1. 先清理可能残留的旧进程（端口 + 虚拟环境下的 python）
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host ("[start.ps1] Port " + $port + " in use, cleaning up...") -ForegroundColor Yellow
    $existing | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2
}

# 2. 启动
$exe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$main = Join-Path $projectRoot "main.py"
if (-not (Test-Path $exe)) { throw "Not found: $exe (run: uv venv / pip install -r requirements.txt)" }
if (-not (Test-Path $main)) { throw "Not found: $main" }

Write-Host ("[start.ps1] Starting backend -> http://localhost:" + $port) -ForegroundColor Green
if ($Background) {
    # 后台启动：隐藏窗口 + 把 stdout/stderr 重定向到日志
    $logDir = Join-Path $projectRoot "logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $logFile = Join-Path $logDir "start.log"
    $proc = Start-Process -FilePath $exe -ArgumentList "`"$main`"" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError "$logFile.err" `
        -PassThru
    Write-Host ("[start.ps1] Background started, PID=" + $proc.Id + ", log=" + $logFile) -ForegroundColor Green
    # 等待端口就绪（最多 20 秒）
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep 1
        $listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listen) {
            Write-Host ("[start.ps1] Service is up on port " + $port + " (took " + ($i + 1) + "s)") -ForegroundColor Green
            return
        }
    }
    Write-Host "[start.ps1] WARNING: port $port not listening after 20s. Check logs\start.log" -ForegroundColor Red
} else {
    & $exe $main
}
