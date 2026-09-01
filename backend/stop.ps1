# stop.ps1 - Stop xianzhi-agent backend
# Usage: .\stop.ps1          # confirm before killing
#        .\stop.ps1 -Force   # skip confirmation
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less files
# as GBK, and non-ASCII comments/strings break parsing.
# With uvicorn --reload the app is a reloader parent + server child. If the
# parent dies, the child can INHERIT the listening socket: the port still
# reports the dead parent PID while a live orphan serves it. So we resolve
# candidates via CIM (path/commandline), kill whole trees with taskkill /T,
# then re-check the port in a retry loop.

param(
    [int]$Port = 8123,
    [switch]$Force
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

function Get-PortOwnerPids {
    param([int]$Port)
    $pids = @()
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conns) { $pids += $conns.OwningProcess }
    $lines = netstat -ano | Select-String (":" + $Port + "\s") | Select-String "LISTENING"
    foreach ($l in $lines) { $pids += [int]($l -split '\s+')[-1] }
    $pids | Sort-Object -Unique
}

function Get-CandidatePids {
    # 1) python from this repo's .venv (CIM ExecutablePath; avoids Get-Process .Path access issues)
    # 2) any python whose commandline mentions main.py / uvicorn / multiprocessing spawn children
    # 3) live children of the above (process tree)
    $venvPy = (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -replace "\\", "\\\\"
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe' or Name='uvicorn.exe'" -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath -match $venvPy) -or
        ($_.CommandLine -and $_.CommandLine -match "main\.py|uvicorn|multiprocessing")
    }
    $pids = @($procs | ForEach-Object { $_.ProcessId })
    $pids += Get-PortOwnerPids -Port $Port
    $all = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" -ErrorAction SilentlyContinue
    foreach ($a in $all) {
        if ($pids -contains $a.ParentProcessId) { $pids += $a.ProcessId }
    }
    $pids | Sort-Object -Unique
}

$candidates = Get-CandidatePids
$live = @($candidates | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })

if ($live.Count -eq 0) {
    Write-Host ("[stop.ps1] Port " + $Port + " is free, nothing to stop.") -ForegroundColor Gray
    return
}

Write-Host ("[stop.ps1] About to terminate " + $live.Count + " process(es):") -ForegroundColor Yellow
foreach ($procId in $live) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($p) {
        $cmd = if ($p.CommandLine) { $p.CommandLine } else { $p.Name }
        if ($cmd.Length -gt 90) { $cmd = $cmd.Substring(0, 90) + "..." }
        Write-Host ("  PID=" + $procId + "  PPID=" + $p.ParentProcessId + "  " + $cmd) -ForegroundColor Gray
    }
}

if (-not $Force) {
    $ans = Read-Host "Confirm terminate? (y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") {
        Write-Host "[stop.ps1] Cancelled." -ForegroundColor Gray
        return
    }
}

for ($round = 1; $round -le 3; $round++) {
    $targets = @(Get-CandidatePids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($targets.Count -eq 0) { break }
    foreach ($procId in $targets) {
        $null = & taskkill /T /F /PID $procId 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("  [KILLED tree] PID=" + $procId) -ForegroundColor Green
        }
    }
    Start-Sleep 1
    $owners = @(Get-PortOwnerPids -Port $Port | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($owners.Count -eq 0) { break }
}

Start-Sleep 1
$remaining = Get-PortOwnerPids -Port $Port
$remainingLive = @($remaining | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
if ($remainingLive.Count -gt 0) {
    Write-Host ("[stop.ps1] WARNING: port " + $Port + " still held by live PID(s): " + ($remainingLive -join ", ") + ". Retry from an elevated terminal.") -ForegroundColor Red
} else {
    Write-Host ("[stop.ps1] Port " + $Port + " is now free.") -ForegroundColor Green
}
