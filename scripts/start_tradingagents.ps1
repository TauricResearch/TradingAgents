[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SetupOnly,
    [switch]$Checkpoint,
    [switch]$ClearCheckpoints,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$InstallMarker = Join-Path $VenvDir ".tradingagents-installed"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function New-ProjectVenv {
    Write-Step "Creating Python virtual environment"

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & py -3 -m venv $VenvDir
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            throw "Python was not found. Install Python 3.10+ and run this launcher again."
        }
        & python -m venv $VenvDir
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Could not create virtual environment at $VenvDir"
    }
}

Set-Location $ProjectRoot

Write-Host "TradingAgents launcher" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path $VenvPython)) {
    New-ProjectVenv
}

& $VenvPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The virtual environment must use Python 3.10 or newer."
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env")) -and (Test-Path (Join-Path $ProjectRoot ".env.example"))) {
    Write-Step "Creating .env from .env.example"
    Copy-Item (Join-Path $ProjectRoot ".env.example") (Join-Path $ProjectRoot ".env")
    Write-Host "Created .env. The CLI can help fill provider API keys during first run."
}

$needsInstall = -not (Test-Path $InstallMarker)
$consoleScript = Join-Path $VenvDir "Scripts\tradingagents.exe"
if (-not (Test-Path $consoleScript)) {
    $needsInstall = $true
}
elseif (Test-Path $InstallMarker) {
    $pyproject = Get-Item (Join-Path $ProjectRoot "pyproject.toml")
    $marker = Get-Item $InstallMarker
    if ($pyproject.LastWriteTimeUtc -gt $marker.LastWriteTimeUtc) {
        $needsInstall = $true
    }
}

if ($SkipInstall) {
    Write-Step "Skipping dependency install"
}
elseif ($needsInstall) {
    Write-Step "Installing project dependencies"
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Invoke-Checked $uv.Source @("pip", "install", "--python", $VenvPython, "-e", ".")
    }
    else {
        Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Checked $VenvPython @("-m", "pip", "install", "-e", ".")
    }
    Set-Content -Path $InstallMarker -Value (Get-Date).ToString("o") -Encoding ASCII
}
else {
    Write-Step "Environment already installed"
}

if ($SetupOnly) {
    Write-Step "Setup complete"
    exit 0
}

Write-Step "Starting TradingAgents CLI"

$runArgs = @("-m", "cli.main", "analyze")
if ($Checkpoint) {
    $runArgs += "--checkpoint"
}
if ($ClearCheckpoints) {
    $runArgs += "--clear-checkpoints"
}
if ($CliArgs) {
    $runArgs += $CliArgs
}

& $VenvPython @runArgs
exit $LASTEXITCODE
