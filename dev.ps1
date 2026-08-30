# dev.ps1 - vitoice (vitoice_fin) dev-mode launcher
# Usage: open Windows PowerShell from Start menu, then:
#   cd G:\Code\vitoice_fin
#   .\dev.ps1
#
# Use case: start Tauri dev mode in a "system terminal" (outside the TRAE sandbox).
# Note: Tauri dev mode = frontend HMR + Rust auto-recompile. It does NOT produce
#       an installer. For that, use `tauri build` (frontend bundle + Rust binary + sidecar).

# ---- 1. Use the REAL cargo from the toolchain (.cargo\bin shims are 0-byte) ----
$toolchainBin = "C:\Users\Administrator\.rustup\toolchains\stable-x86_64-pc-windows-msvc\bin"
$env:PATH = "$toolchainBin;C:\Users\Administrator\.cargo\bin;" + $env:PATH
$env:CARGO_HOME = "C:\Users\Administrator\.cargo"
$env:RUSTUP_HOME = "C:\Users\Administrator\.rustup"

# ---- 2. Clear a broken proxy that breaks dependency fetching ----
$env:HTTP_PROXY = $null
$env:HTTPS_PROXY = $null
$env:http_proxy = $null
$env:https_proxy = $null

# ---- 3. Move to the script's own directory (must be project root; beforeDevCommand is `cd frontend`) ----
Set-Location "$PSScriptRoot"

# ---- 4. Verify cargo is reachable ----
$cargoVer = & "$toolchainBin\cargo.exe" --version 2>&1
Write-Host "[dev] Cargo: $cargoVer" -ForegroundColor Green

Write-Host "[dev] Starting Tauri (vitoice) in dev mode..." -ForegroundColor Cyan
Write-Host "[dev] Tauri dev mode will automatically:" -ForegroundColor Cyan
Write-Host "  1. Start Vite dev server via beforeDevCommand (frontend HMR, instant refresh on edit)" -ForegroundColor Gray
Write-Host "  2. Compile and run the Rust backend (src-tauri); edits to .rs auto-recompile and restart" -ForegroundColor Gray
Write-Host "  3. Load the frontend from http://127.0.0.1:5173 (tauri.conf.json devUrl)" -ForegroundColor Gray
Write-Host ""

# ---- 5. (Optional) Also start the Python backend (FastAPI @ backend/app/main.py) ----
# IMPORTANT: Tauri does NOT launch Python as a sidecar today (no sidecar logic in main.rs),
#            so dev mode only covers frontend + Rust by default. To run the backend locally,
#            set the variable below to $true. It uses backend\.venv python to run uvicorn
#            on 127.0.0.1:8765 (matching the CSP in tauri.conf.json).
#
# "Restart uvicorn manually (without restarting Tauri):"
#   In a SEPARATE PowerShell window, run these two commands:
#     taskkill /F /FI "WINDOWTITLE eq uvicorn*" 2>$null
#     Start-Process -FilePath "backend\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--reload","--host","127.0.0.1","--port","8765" -WorkingDirectory "backend"
#
# "Is uvicorn auto-reload working?"
#   - --reload is enabled (watches backend/*.py for changes)
#   - After saving a .py file, wait ~1 second — the terminal will show a restart message
#   - Verify with: curl http://127.0.0.1:8765/health (should return {"status":"ok"})
#
$StartPythonBackend = $true
$pythonJob = $null
if ($StartPythonBackend) {
    $venvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
    $pyExe = if (Test-Path $venvPython) { $venvPython } else { "python" }
    # Use isolated dev database (backend/data/vitoice_dev.db) — NOT ~/.vitoice/
    $env:VITOICE_ENV = "dev"
    Write-Host "[dev] Starting Python backend (uvicorn, --reload)..." -ForegroundColor Cyan
    Write-Host "[dev] VITOICE_ENV=dev -> database: backend/data/vitoice_dev.db" -ForegroundColor Gray
    Write-Host "[dev] Backend will auto-reload on .py changes. Watch this window for reload logs." -ForegroundColor Gray
    Write-Host "[dev] To restart manually: taskkill /F /FI `"WINDOWTITLE eq uvicorn*`" 2>`$null ; then re-run dev.ps1" -ForegroundColor DarkGray
    $pythonJob = Start-Process -FilePath $pyExe `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8765" `
        -WorkingDirectory (Join-Path $PSScriptRoot "backend") `
        -PassThru
}

try {
    # ---- 6. Use the locally installed Tauri CLI (frontend/node_modules/.bin/tauri, pinned ^2.0.2) ----
    # Calling the local binary avoids `npx tauri` pulling an inconsistent latest version over the network.
    $tauriCli = Join-Path $PSScriptRoot "frontend\node_modules\.bin\tauri.cmd"
    if (Test-Path $tauriCli) {
        & $tauriCli dev
    } else {
        Write-Host "[dev] Local Tauri CLI not found, falling back to npx (requires network)..." -ForegroundColor Yellow
        npx tauri dev
    }
}
finally {
    # Clean up the Python backend process on exit to avoid orphan processes
    if ($pythonJob -and -not $pythonJob.HasExited) {
        Write-Host "[dev] Stopping Python backend..." -ForegroundColor Gray
        Stop-Process -Id $pythonJob.Id -Force -ErrorAction SilentlyContinue
    }
}
