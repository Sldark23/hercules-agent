# Hercules Agent — Bootstrap installer for Windows (PowerShell)
# Delegates to install.js (the canonical installer)
# This script ensures Node.js is available, then runs install.js.

$ErrorActionPreference = 'Stop'

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Help / Version ─────────────────────────────
if ($args -contains '--help' -or $args -contains '-h') {
    Write-Host "Hercules Agent Installer" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File install.ps1"
    Write-Host "  install.ps1 --help       Show this help"
    Write-Host "  install.ps1 --version    Show version"
    Write-Host ""
    Write-Host "Environment variables:"
    Write-Host "  HERCULES_HOME    Install directory (default: ~\.hercules\agent)"
    Write-Host "  HERCULES_BIN     Binary directory (default: ~\.hercules\bin)"
    exit 0
}

if ($args -contains '--version' -or $args -contains '-v') {
    & node "$ScriptPath\install.js" --version 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "0.1.0" }
    exit 0
}

# ── Check Node.js ──────────────────────────────
try {
    $nodeVer = node --version
    $majorVer = [int]($nodeVer -replace 'v', '' -split '\.')[0]
    if ($majorVer -lt 22) {
        Write-Host "Node.js >= 22 required (found $nodeVer)" -ForegroundColor Red
        exit 1
    }
    Write-Host "Node.js $nodeVer found" -ForegroundColor Green
} catch {
    Write-Host "Node.js is not installed." -ForegroundColor Red
    Write-Host "Download from: https://nodejs.org/en/download/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing Node.js, re-run:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File install.ps1" -ForegroundColor Yellow
    exit 1
}

# ── Delegate to install.js ─────────────────────
Write-Host "Running installer..." -ForegroundColor Green
Set-Location $ScriptPath
& node "$ScriptPath\install.js" @args
exit $LASTEXITCODE
