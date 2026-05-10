param(
    [string]$BaseUrl = "http://localhost:9000",
    [string]$GoogleApiKey = "",
    [string]$EnvFilePath = ".env",
    [switch]$UseEnvFileKey,
    [switch]$Rebuild,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

if (-not $PSBoundParameters.ContainsKey("UseEnvFileKey")) {
    $UseEnvFileKey = $true
}

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Wait-Health {
    param(
        [string]$Url,
        [int]$MaxAttempts = 30,
        [int]$DelaySeconds = 2
    )

    $healthUrl = "$Url/healthz"
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200 -and $resp.Content -match "ok") {
                Write-Host "Health check passed at attempt $i" -ForegroundColor Green
                return
            }
        }
        catch {
            # keep retrying until max attempts
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Service did not become healthy at $healthUrl after $MaxAttempts attempts."
}

function Get-DotenvValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path -Path $Path)) {
        return ""
    }

    $lines = Get-Content -Path $Path
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $prefix = "$Key="
        if ($trimmed.StartsWith($prefix)) {
            return $trimmed.Substring($prefix.Length)
        }
    }
    return ""
}

if ($Rebuild) {
    Write-Step "Rebuilding and recreating tradingagents-api container"
    docker compose up -d --build --force-recreate tradingagents-api
}

Write-Step "Waiting for API health endpoint"
Wait-Health -Url $BaseUrl

$effectiveGoogleApiKey = $GoogleApiKey
if (-not $effectiveGoogleApiKey -and $UseEnvFileKey) {
    $effectiveGoogleApiKey = Get-DotenvValue -Path $EnvFilePath -Key "GOOGLE_API_KEY"
    if ($effectiveGoogleApiKey) {
        Write-Host "Loaded GOOGLE_API_KEY from $EnvFilePath." -ForegroundColor Green
    }
}

if ($effectiveGoogleApiKey) {
    Write-Step "Setting GOOGLE_API_KEY via API"
    $body = @{ value = $effectiveGoogleApiKey } | ConvertTo-Json -Compress
    $setResp = Invoke-RestMethod -Method Put -Uri "$BaseUrl/env/GOOGLE_API_KEY" -ContentType "application/json" -Body $body
    if (-not $setResp.exists) {
        throw "Failed to set GOOGLE_API_KEY via API."
    }
    Write-Host "GOOGLE_API_KEY updated via API." -ForegroundColor Green
}
else {
    Write-Host "GOOGLE_API_KEY not provided and not found in $EnvFilePath. Skipping key update." -ForegroundColor Yellow
}

Write-Step "Quick page checks"
$pages = @(
    "/ui",
    "/batching",
    "/settings",
    "/completed",
    "/requests/closed?format=html"
)
foreach ($p in $pages) {
    $url = "$BaseUrl$p"
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -ne 200) {
        throw "Endpoint check failed: $url -> $($resp.StatusCode)"
    }
    Write-Host "$url -> $($resp.StatusCode)" -ForegroundColor Green
}

if (-not $SkipTests) {
    Write-Step "Running post-deploy smoke tests"
    .\.venv\Scripts\python.exe -m pytest tests/test_api_ui_smoke_post_deploy.py -q
}
else {
    Write-Host "Skipping pytest smoke tests due to -SkipTests." -ForegroundColor Yellow
}

Write-Step "Post-deploy validation complete"
Write-Host "Base URL: $BaseUrl" -ForegroundColor Green
