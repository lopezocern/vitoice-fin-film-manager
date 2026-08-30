param(
  [int]$Port = 8765,
  [switch]$Dev
)
# start-backend.ps1 - 独立、脱离父终端的后端启动器
# 用法（在 project root 打开 PowerShell）：
#   .\start-backend.ps1              # 默认 8765，prod 数据库(~/.vitoice/vitoice.db)
#   .\start-backend.ps1 -Port 11661  # 指定端口
#   .\start-backend.ps1 -Dev         # VITOICE_ENV=dev，使用 backend/data/vitoice_dev.db
# 通过 Start-Process 启动，后端进程与当前 PowerShell 窗口生命周期解耦，
# 关闭本窗口不会杀掉后端（区别于 dev.ps1 的 finally 清理逻辑）。

$root = $PSScriptRoot
$venv = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }

if ($Dev) { $env:VITOICE_ENV = "dev" }

$old = (Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue).OwningProcess
if ($old) {
  Write-Host "[start-backend] Port $Port occupied by pid $old, killing..." -ForegroundColor Yellow
  Stop-Process -Id $old -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

$proc = Start-Process -FilePath $venv `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", $Port `
  -WorkingDirectory (Join-Path $root "backend") `
  -PassThru

Write-Host "[start-backend] Backend PID $($proc.Id) launched on http://127.0.0.1:$Port (detached)" -ForegroundColor Green
Start-Sleep -Seconds 4
try {
  $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -ErrorAction Stop
  Write-Host "[start-backend] Health OK: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
  Write-Host "[start-backend] Health FAILED: $_" -ForegroundColor Red
}
