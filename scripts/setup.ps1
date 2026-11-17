<#
.SYNOPSIS
    Day 1 Setup Script for Territory Control and Hotspot Analysis.
.DESCRIPTION
    Checks prerequisites (Python 3.11, Java 17+), creates an isolated .venv,
    upgrades pip, installs required packages, and validates imports.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DAY 1 SETUP: GEOSPATIAL BIG DATA & TERRITORY CONTROL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Inspect Python
Write-Host "`n[1/6] Checking Python installation..." -ForegroundColor Yellow
$PythonCandidates = @(
    "C:\purva\python.exe",
    "py",
    "python"
)

$SystemPython = $null
foreach ($cand in $PythonCandidates) {
    try {
        if ($cand -eq "py") {
            $ver = & py -3.11 -c "import sys; print(sys.version)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                $SystemPython = "py -3.11"
                Write-Host "  Found Python via 'py -3.11': $ver" -ForegroundColor Green
                break
            }
        } else {
            $testCmd = Get-Command $cand -ErrorAction SilentlyContinue
            if ($testCmd) {
                $ver = & $cand -c "import sys; print(sys.version)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $ver) {
                    $SystemPython = $cand
                    Write-Host "  Found Python at '$cand': $ver" -ForegroundColor Green
                    break
                }
            }
        }
    } catch {}
}

if (-not $SystemPython) {
    Write-Error "Python 3.11 was not found. Please install Python 3.11 (64-bit)."
    exit 1
}

# 2. Inspect Java & JAVA_HOME
Write-Host "`n[2/6] Checking Java and JAVA_HOME..." -ForegroundColor Yellow
$JavaHome = $env:JAVA_HOME
if (-not $JavaHome -or -not (Test-Path "$JavaHome\bin\java.exe")) {
    $PossibleJdks = @(
        "C:\Program Files\Java\jdk-23",
        "C:\Program Files\Java\jdk-17",
        "C:\Program Files\Eclipse Adoptium\jdk-17"
    )
    foreach ($cand in $PossibleJdks) {
        if (Test-Path "$cand\bin\java.exe") {
            $env:JAVA_HOME = $cand
            $JavaHome = $cand
            Write-Host "  Configured JAVA_HOME for session: $JavaHome" -ForegroundColor Green
            break
        }
    }
}

if (-not $JavaHome -or -not (Test-Path "$JavaHome\bin\java.exe")) {
    Write-Warning "JAVA_HOME is not pointing to a valid JDK. PySpark requires Java JDK 17+."
    Write-Host "  Please install JDK 17 or 23 from https://adoptium.net or Oracle." -ForegroundColor Red
} else {
    Write-Host "  JAVA_HOME: $JavaHome" -ForegroundColor Green
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $javaVer = & "$JavaHome\bin\java.exe" -version 2>&1
    $ErrorActionPreference = $oldEap
    Write-Host "  Java Version: $($javaVer[0])" -ForegroundColor Green
}

# 3. Create Virtual Environment (.venv)
Write-Host "`n[3/6] Configuring virtual environment (.venv)..." -ForegroundColor Yellow
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "  Creating isolated virtual environment at $VenvDir..." -ForegroundColor Cyan
    if ($SystemPython -eq "py -3.11") {
        & py -3.11 -m venv $VenvDir
    } else {
        & $SystemPython -m venv $VenvDir
    }
} else {
    Write-Host "  Existing .venv detected at $VenvDir" -ForegroundColor Green
}

# 4. Pip Cache & Temp Paths (Avoid filling Drive C:)
$PipCacheDir = "D:\pip_cache"
$TmpDir = "D:\tmp"
if (Test-Path "D:\") {
    New-Item -ItemType Directory -Force -Path $PipCacheDir, $TmpDir | Out-Null
    $env:TEMP = $TmpDir
    $env:TMP = $TmpDir
}

# 5. Upgrade Pip and Install Dependencies
Write-Host "`n[4/6] Upgrading pip and installing requirements..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip

$ReqFile = Join-Path $ProjectRoot "requirements.txt"
if (Test-Path $ReqFile) {
    if (Test-Path "D:\") {
        & $VenvPython -m pip install --cache-dir $PipCacheDir -r $ReqFile
    } else {
        & $VenvPython -m pip install -r $ReqFile
    }
}

# 6. Windows Hadoop / PySpark Native Binaries
$HadoopBin = Join-Path $ProjectRoot "hadoop\bin"
if (-not (Test-Path "$HadoopBin\winutils.exe") -or -not (Test-Path "$HadoopBin\hadoop.dll")) {
    Write-Host "  Configuring local Windows Hadoop binaries (winutils.exe, hadoop.dll)..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $HadoopBin | Out-Null
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/cdarlint/winutils/master/hadoop-3.3.6/bin/winutils.exe" -OutFile "$HadoopBin\winutils.exe"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/cdarlint/winutils/master/hadoop-3.3.6/bin/hadoop.dll" -OutFile "$HadoopBin\hadoop.dll"
}

# 7. Verify Imports & Technology Versions
Write-Host "`n[5/6] Verifying library imports..." -ForegroundColor Yellow
$VerifyScript = @"
import sys
packages = ['pyspark', 'h3', 'pandas', 'numpy', 'pyarrow', 'yaml', 'pytest']
missing = []
for p in packages:
    try:
        mod = __import__(p)
        ver = getattr(mod, '__version__', 'installed')
        print(f'  [OK] {p:<12} version {ver}')
    except ImportError as e:
        print(f'  [FAIL] {p:<12}: {e}')
        missing.append(p)
if missing:
    sys.exit(1)
"@

& $VenvPython -c $VerifyScript
if ($LASTEXITCODE -ne 0) {
    Write-Error "One or more required dependencies failed to import."
    exit 1
}

Write-Host "`n[6/6] Environment Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
