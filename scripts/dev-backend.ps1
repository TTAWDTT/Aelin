param(
  [int]$Port = 8000,
  [string]$Host = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'

$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
  $commandLine = [string]($proc.CommandLine)
  $looksLikeAelinBackend =
    $commandLine -match 'uvicorn' -and
    $commandLine -match 'app\.main:app' -and
    $commandLine -match 'Aelin\\backend'

  if ($looksLikeAelinBackend) {
    Write-Host "Stopping existing Aelin backend on port $Port (PID=$($listener.OwningProcess))..."
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Milliseconds 600
  } else {
    throw "Port $Port is already in use by PID=$($listener.OwningProcess). Refusing to kill a non-Aelin process."
  }
}

Set-Location $backendDir
python -m uvicorn app.main:app --reload --host $Host --port $Port
