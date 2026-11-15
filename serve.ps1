# serve.ps1 - start/stop local dev servers independent of any agent session
#
# Why this exists:
#   uvicorn / vite used to be started as "session background jobs". They lived in
#   the same Windows Job object as later commands such as `npm run check`. When any
#   job was torn down, the whole group got Ctrl+C'd (exit 0xC000013A = 3221225786),
#   which looks like "the command died / the session restarted".
#   Start-Process decouples the servers from this console, and the launcher returns
#   immediately, so gate commands can no longer be collaterally killed.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less .ps1 using
#       the ANSI codepage, so non-ASCII text here becomes mojibake and parse errors.
#
# Usage:
#   .\serve.ps1            # start backend(8765) + frontend(5173)
#   .\serve.ps1 -Status    # show status
#   .\serve.ps1 -Stop      # stop (kills by port, only if it looks like this project)
#
# Logs: .tmp\serve\backend.log / backend.err.log / vite.log / vite.err.log
param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$logDir = Join-Path $root '.tmp\serve'
$pidFile = Join-Path $logDir 'pids.json'
$backendPort = 8765
$frontendPort = 5173

function Get-PortOwner([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { return ($conn | Select-Object -ExpandProperty OwningProcess -Unique) }
    return @()
}

function Show-Status {
    foreach ($pair in @(@{ name = 'backend'; port = $backendPort }, @{ name = 'frontend'; port = $frontendPort })) {
        $owners = @(Get-PortOwner $pair.port)
        if ($owners.Count -gt 0) {
            Write-Host ("[serve] {0,-8} :{1}  listening (pid {2})" -f $pair.name, $pair.port, ($owners -join ',')) -ForegroundColor Green
        } else {
            Write-Host ("[serve] {0,-8} :{1}  stopped" -f $pair.name, $pair.port) -ForegroundColor DarkGray
        }
    }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/health" -TimeoutSec 3
        Write-Host ("[serve] health: " + $h.status) -ForegroundColor Green
    } catch {
        Write-Host "[serve] health: backend not responding" -ForegroundColor DarkGray
    }
}

function Stop-Servers {
    foreach ($port in @($backendPort, $frontendPort)) {
        $owners = @(Get-PortOwner $port)
        foreach ($procId in $owners) {
            $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if (-not $p) { continue }
            $cmd = ''
            try { $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$procId").CommandLine } catch { }
            if ($cmd -match 'uvicorn|vite|vitoice') {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host ("[serve] stopped {0} (pid {1}, :{2})" -f $p.ProcessName, $procId, $port) -ForegroundColor Yellow
            } else {
                Write-Host ("[serve] :{0} held by pid {1} ({2}) - not this project, skipped" -f $port, $procId, $p.ProcessName) -ForegroundColor Red
            }
        }
    }
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
    Show-Status
}

if ($Stop) { Stop-Servers; return }
if ($Status) { Show-Status; return }

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Do not start a second instance: two `uvicorn --reload` would fight over the port
if ((@(Get-PortOwner $backendPort)).Count -gt 0 -and (@(Get-PortOwner $frontendPort)).Count -gt 0) {
    Write-Host '[serve] both services already running:' -ForegroundColor Green
    Show-Status
    return
}

$env:VITOICE_ENV = 'dev'
$venvPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
$pyExe = if (Test-Path $venvPython) { $venvPython } else { 'python' }

$pids = @{}

if ((@(Get-PortOwner $backendPort)).Count -eq 0) {
    $pids.backend = (Start-Process -FilePath $pyExe `
            -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', "$backendPort" `
            -WorkingDirectory (Join-Path $root 'backend') `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'backend.log') `
            -RedirectStandardError (Join-Path $logDir 'backend.err.log')).Id
    Write-Host ("[serve] backend starting (pid {0}) -> :{1}" -f $pids.backend, $backendPort) -ForegroundColor Cyan
}

if ((@(Get-PortOwner $frontendPort)).Count -eq 0) {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    $npmExe = if ($npm) { $npm.Source } else { 'npm' }
    $pids.frontend = (Start-Process -FilePath $npmExe `
            -ArgumentList 'run', 'dev' `
            -WorkingDirectory (Join-Path $root 'frontend') `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'vite.log') `
            -RedirectStandardError (Join-Path $logDir 'vite.err.log')).Id
    Write-Host ("[serve] frontend starting (pid {0}) -> :{1}" -f $pids.frontend, $frontendPort) -ForegroundColor Cyan
}

$pids | ConvertTo-Json | Set-Content -Path $pidFile -Encoding utf8

# Wait for both ports (max 30s) so the printed URLs are usable immediately
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    if ((@(Get-PortOwner $backendPort)).Count -gt 0 -and (@(Get-PortOwner $frontendPort)).Count -gt 0) { break }
    Start-Sleep -Milliseconds 700
}

Show-Status
Write-Host ''
Write-Host '  frontend  http://127.0.0.1:5173' -ForegroundColor Green
Write-Host '  backend   http://127.0.0.1:8765/docs' -ForegroundColor Green
Write-Host '  stop      .\serve.ps1 -Stop' -ForegroundColor DarkGray
