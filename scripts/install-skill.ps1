param(
    [string]$Destination,
    [switch]$SkipFrameworkInstall,
    [switch]$SkipUserEnvironment
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$frameworkRoot = Join-Path $repositoryRoot "framework"
$skillSource = Join-Path $repositoryRoot "skill\a-share-tradingagents"
$skillTarget = if ($Destination) {
    $Destination
} else {
    Join-Path $env:USERPROFILE ".codex\skills\a-share-tradingagents"
}
$pythonPath = Join-Path $frameworkRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $frameworkRoot)) {
    throw "Framework directory not found: $frameworkRoot"
}

if (-not $SkipFrameworkInstall) {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        python -m venv (Join-Path $frameworkRoot ".venv")
    }

    & $pythonPath -m pip install -e $frameworkRoot
}

New-Item -ItemType Directory -Path $skillTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $skillSource "SKILL.md") -Destination $skillTarget -Force
Copy-Item -LiteralPath (Join-Path $skillSource "agents") -Destination $skillTarget -Recurse -Force

if (-not $SkipUserEnvironment) {
    [Environment]::SetEnvironmentVariable(
        "A_SHARE_TRADINGAGENTS_HOME",
        $frameworkRoot,
        "User"
    )
}

Write-Host "Installed Skill: $skillTarget"
Write-Host "Framework: $frameworkRoot"
if ($SkipUserEnvironment) {
    Write-Host "Restart Codex so it can discover the Skill."
} else {
    Write-Host "Restart Codex so it can discover the Skill and user environment variable."
}
