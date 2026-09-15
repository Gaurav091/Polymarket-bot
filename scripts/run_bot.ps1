# Launches the Polymarket survival bot in a visible terminal.
# The bot loops internally (news -> classify -> trade -> monitor -> survive);
# this script only starts it and keeps the window alive on crash so the
# death report stays readable.
param(
    [switch]$Live   # omit = paper mode (safe); -Live = real money via CLOB
)

$botDir = Split-Path -Parent $PSScriptRoot
$python = Join-Path $botDir ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "ERROR: .venv not found at $python" -ForegroundColor Red
    Write-Host "Run: uv venv .venv --python 3.12; uv pip install --python .venv\Scripts\python.exe -r requirements.txt"
    exit 1
}

if ($Live) {
    # Safety confirmation for real-money mode
    Write-Host "WARNING: LIVE MODE - real money will be traded on Polymarket." -ForegroundColor Red
    $confirm = Read-Host "Type LIVE to continue"
    if ($confirm -ne "LIVE") {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 1
    }
    $env:DRY_RUN = "false"
} else {
    $env:DRY_RUN = "true"
}

Write-Host "Starting Polymarket Survival Bot ($($(if ($Live) {'LIVE'} else {'PAPER'})) mode)..." -ForegroundColor Green
& $python -m bot.main
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Bot exited with code $exitCode." -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Yellow" })
if ($exitCode -ne 0) {
    Write-Host "Check data\trades.db survival_events table for the death report." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
}
