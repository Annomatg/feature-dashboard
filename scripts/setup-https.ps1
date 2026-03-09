# HTTPS Setup for Feature Dashboard (Windows)
# Installs mkcert and generates trusted localhost certificates for the Vite dev server.
#
# Usage:
#   .\scripts\setup-https.ps1
#
# After running, start the dev server with:
#   cd frontend && npm run dev
# The Vite dev server will auto-detect the certs and enable HTTPS.

$ErrorActionPreference = "Stop"

$certsDir = Join-Path $PSScriptRoot "..\frontend\certs"
$certFile = Join-Path $certsDir "localhost.pem"
$keyFile  = Join-Path $certsDir "localhost-key.pem"

Write-Host "=== Feature Dashboard HTTPS Setup ===" -ForegroundColor Cyan

# Create certs directory
if (-not (Test-Path $certsDir)) {
    New-Item -ItemType Directory -Path $certsDir | Out-Null
    Write-Host "[+] Created $certsDir"
}

# Check if mkcert is available
$mkcert = $null
try {
    $mkcert = Get-Command mkcert -ErrorAction Stop
    Write-Host "[+] mkcert found: $($mkcert.Source)"
} catch {
    Write-Host "[!] mkcert not found. Attempting to install via winget..." -ForegroundColor Yellow
    try {
        winget install FiloSottile.mkcert --silent
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        $mkcert = Get-Command mkcert -ErrorAction Stop
        Write-Host "[+] mkcert installed successfully."
    } catch {
        Write-Host "[!] winget install failed. Please install mkcert manually:" -ForegroundColor Red
        Write-Host "    https://github.com/FiloSottile/mkcert/releases" -ForegroundColor Red
        Write-Host "    Or via Chocolatey: choco install mkcert" -ForegroundColor Red
        exit 1
    }
}

# Install the local CA (requires admin the first time)
Write-Host "[+] Installing local Certificate Authority (may prompt for admin)..."
& mkcert -install

# Generate certificates for localhost
Write-Host "[+] Generating certificate for localhost..."
Push-Location $certsDir
try {
    & mkcert -key-file localhost-key.pem -cert-file localhost.pem localhost 127.0.0.1 ::1
} finally {
    Pop-Location
}

if ((Test-Path $certFile) -and (Test-Path $keyFile)) {
    Write-Host ""
    Write-Host "[OK] HTTPS certificates generated:" -ForegroundColor Green
    Write-Host "     Cert: $certFile"
    Write-Host "     Key:  $keyFile"
    Write-Host ""
    Write-Host "Start the dev server normally — Vite will auto-detect the certs:" -ForegroundColor Cyan
    Write-Host "  cd frontend && npm run dev"
    Write-Host ""
    Write-Host "Your app will be available at https://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Certificate generation failed." -ForegroundColor Red
    exit 1
}
