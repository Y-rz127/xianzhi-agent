# start.ps1 - 一键启动先知智能体
# 用法：.\start.ps1               # Foreground (Ctrl+C to stop)
#       .\start.ps1 -Background   # Background (silent, returns immediately)
#
# [!] 本文件必须保存为 UTF-8 **with BOM**。PowerShell 5.1 对无 BOM 的脚本按系统
#     ANSI(936/GBK) 解码，中文注释和字符串会变乱码、连字符串引号一起吃掉，直接
#     ParserError 整个脚本起不来（2026-10-25 踩过）。

param(
    [switch]$Background
)

# 强制 UTF-8 输出
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot   # backend/ directory
$repoRoot = Split-Path -Parent $PSScriptRoot  # repo root (holds .venv)
$port = 8123

# 1. 先清理可能残留的旧进程（端口 + 虚拟环境下的 python）
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host ("[start.ps1] Port " + $port + " in use, cleaning up...") -ForegroundColor Yellow
    $existing | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2
}

# 2. 启动
$exe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$main = Join-Path $projectRoot "main.py"
if (-not (Test-Path $exe)) { throw "Not found: $exe (run: uv venv / pip install -r requirements.txt)" }
if (-not (Test-Path $main)) { throw "Not found: $main" }

# 1.5 原生扩展自检：Windows 智能应用控制/AppLocker 会拦 venv 里未建立信誉的 .pyd，
#     症状是 import sqlalchemy 直接失败（PG 记忆层、pgvector 检索一起挂，但服务"看着"启动成功）。
#     脚本把 SQLAlchemy 切成纯 Python 实现；退出码 2=刚修好，1=需要人工放行。
#     自检失败不阻断启动（服务仍能跑，只是记忆/检索降级），所以只告警不 throw。
$cextGuard = Join-Path $projectRoot "scripts\ensure_cext_fallback.py"
if (Test-Path $cextGuard) {
    try {
        & $exe $cextGuard
        if ($LASTEXITCODE -eq 1) {
            Write-Host "[start.ps1] WARNING: venv native extension blocked by policy, see [cext] log above" -ForegroundColor Red
        }
    } catch {
        Write-Host ("[start.ps1] WARNING: cext self-check skipped - " + $_.Exception.Message) -ForegroundColor Yellow
    }
}

Write-Host ("[start.ps1] Starting backend -> http://localhost:" + $port) -ForegroundColor Green
if ($Background) {
    # 后台启动：隐藏窗口，进程独立于当前会话。
    #
    # [!] 不要给 Start-Process 加 -RedirectStandardOutput / -RedirectStandardError。
    #     本机环境同时存在 http_proxy 与 HTTP_PROXY（仅大小写不同），带重定向时
    #     Start-Process 会把环境变量复制进忽略大小写的字典，直接抛
    #     ArgumentException「已添加项。字典中的关键字:"http_proxy"所添加的关键字:"HTTP_PROXY"」，
    #     表现是脚本静默退出、start.log 永远 0 字节（2026-10-25 排查）。
    #     启动日志看 backend/logs/xianzhi_*.log，那里才是完整记录。
    try {
        $proc = Start-Process -FilePath $exe -ArgumentList "`"$main`"" `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -PassThru -ErrorAction Stop
    } catch {
        Write-Host ("[start.ps1] ERROR: background start failed - " + $_.Exception.Message) -ForegroundColor Red
        throw
    }
    Write-Host ("[start.ps1] Background started, PID=" + $proc.Id + " (log: logs/xianzhi_*.log)") -ForegroundColor Green
    # 等待端口就绪（最多 20 秒）
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep 1
        $listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listen) {
            Write-Host ("[start.ps1] Service is up on port " + $port + " (took " + ($i + 1) + "s)") -ForegroundColor Green
            return
        }
    }
    Write-Host "[start.ps1] WARNING: port $port not listening after 20s. Check logs\xianzhi_*.log" -ForegroundColor Red
} else {
    & $exe $main
}
