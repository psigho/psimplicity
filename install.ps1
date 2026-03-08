$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Psimplicity 1-Click Installer" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check for Git
try {
    $null = Get-Command git -ErrorAction Stop
    Write-Host "[OK] Git is installed." -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Git is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please download and install Git: https://git-scm.com/downloads" -ForegroundColor Yellow
    Exit
}

# 2. Check for Python
try {
    $null = Get-Command python -ErrorAction Stop
    $pyVersion = (& python --version 2>&1)
    Write-Host "[OK] Python is installed ($pyVersion)." -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please download Python 3.10+: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "IMPORTANT: Check 'Add Python to PATH' during installation!" -ForegroundColor Yellow
    Exit
}

# 3. Target Directory
$defaultDir = "$HOME\Documents"
$installDir = Read-Host "Where would you like to install Psimplicity? (Press Enter for Default: $defaultDir)"

if ([string]::IsNullOrWhiteSpace($installDir)) {
    $installDir = $defaultDir
}

if (-Not (Test-Path $installDir)) {
    Write-Host "Creating directory $installDir..." -ForegroundColor DarkGray
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
}

Set-Location $installDir
Write-Host ""
Write-Host "Downloading Psimplicity into $installDir..." -ForegroundColor Cyan

# 4. Clone Repo
if (Test-Path "psimplicity") {
    Write-Host "[WARNING] Folder 'psimplicity' already exists. Pulling latest updates..." -ForegroundColor Yellow
    Set-Location "psimplicity"
    git pull origin main
}
else {
    git clone https://github.com/psigho/psimplicity.git
    Set-Location "psimplicity"
}

# 5. Launch START.bat
Write-Host ""
Write-Host "Installation successful! Launching the app..." -ForegroundColor Green
Write-Host ""

# Launch START.bat in a new persist window so the user sees the setup
Start-Process "cmd.exe" -ArgumentList "/k START.bat"
