param(
    [string]$VaultComposeFile = "vault-local/docker-compose.yml",
    [string]$UnsealKeyFile = ".vault_unseal_key.local",
    [string]$RootTokenFile = ".vault_root_token.local",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Step)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Step (exit code $LASTEXITCODE)"
    }
}

function Get-EnvValue {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    }
    return $value
}

function Upsert-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)

    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -Path $Path
    }

    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$Key\s*=") {
            $lines[$i] = "$Key=$Value"
            $updated = $true
        }
    }

    if (-not $updated) {
        $lines += "$Key=$Value"
    }

    Set-Content -Path $Path -Value $lines -Encoding ascii
}

Write-Host "Starting local Vault stack..."
Invoke-Checked -Step "start vault stack" -Command { docker compose -f $VaultComposeFile up -d }

$vaultStatus = $null
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    $vaultStatus = docker compose -f $VaultComposeFile exec -T vault sh -lc "export VAULT_ADDR=http://127.0.0.1:8200; vault status -format=json" 2>$null
    if (-not [string]::IsNullOrWhiteSpace($vaultStatus)) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    throw "Unable to read Vault status"
}
$statusObj = $vaultStatus | ConvertFrom-Json

if (-not $statusObj.initialized) {
    Write-Host "Vault is not initialized. Initializing..."
    $initJson = docker compose -f $VaultComposeFile exec -T vault sh -lc "export VAULT_ADDR=http://127.0.0.1:8200; vault operator init -key-shares=1 -key-threshold=1 -format=json"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize Vault"
    }
    $initObj = $initJson | ConvertFrom-Json

    $initObj.unseal_keys_b64[0] | Out-File -FilePath $UnsealKeyFile -Encoding ascii -NoNewline
    $initObj.root_token | Out-File -FilePath $RootTokenFile -Encoding ascii -NoNewline
    Write-Host "Saved unseal key to $UnsealKeyFile and root token to $RootTokenFile"
}

$unsealKey = (Get-Content -Path $UnsealKeyFile -Raw).Trim()
$rootToken = (Get-Content -Path $RootTokenFile -Raw).Trim()

$envToken = Get-EnvValue -Name "VAULT_TOKEN"
if (-not [string]::IsNullOrWhiteSpace($envToken)) {
    $rootToken = $envToken.Trim()
}

$vaultStatus = docker compose -f $VaultComposeFile exec -T vault sh -lc "export VAULT_ADDR=http://127.0.0.1:8200; vault status -format=json"
$statusObj = $vaultStatus | ConvertFrom-Json
if ($statusObj.sealed) {
    Write-Host "Unsealing Vault..."
    docker compose -f $VaultComposeFile exec -T vault sh -lc "export VAULT_ADDR=http://127.0.0.1:8200; vault operator unseal $unsealKey" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to unseal Vault"
    }
}

docker compose -f $VaultComposeFile exec -T `
    -e VAULT_ADDR=http://127.0.0.1:8200 `
    -e VAULT_TOKEN=$rootToken `
    vault sh -lc 'vault token lookup > /dev/null' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Vault token is invalid for this initialized instance. Provide VAULT_TOKEN env var with a valid token or reset vault-local/data and rerun bootstrap."
}

$googleKey = Get-EnvValue -Name "GOOGLE_API_KEY"
$openrouterKey = Get-EnvValue -Name "OPENROUTER_API_KEY"

if ([string]::IsNullOrWhiteSpace($googleKey) -or [string]::IsNullOrWhiteSpace($openrouterKey)) {
    Write-Host "Skipped seeding provider keys because GOOGLE_API_KEY or OPENROUTER_API_KEY is empty in host environment."
    Write-Host "Vault is initialized/unsealed and ready."
    exit 0
}

Write-Host "Seeding provider keys into Vault path secret/tradingagents/api-keys..."
docker compose -f $VaultComposeFile exec -T `
    -e VAULT_ADDR=http://127.0.0.1:8200 `
    -e VAULT_TOKEN=$rootToken `
    -e GOOGLE_API_KEY=$googleKey `
    -e OPENROUTER_API_KEY=$openrouterKey `
    vault sh -lc 'vault kv put secret/tradingagents/api-keys GOOGLE_API_KEY="$GOOGLE_API_KEY" OPENROUTER_API_KEY="$OPENROUTER_API_KEY"' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to seed provider keys into Vault"
}

Upsert-EnvValue -Path $EnvFile -Key "VAULT_ENABLED" -Value "true"
Upsert-EnvValue -Path $EnvFile -Key "VAULT_ADDR" -Value "http://host.docker.internal:8200"
Upsert-EnvValue -Path $EnvFile -Key "VAULT_TOKEN" -Value $rootToken
Upsert-EnvValue -Path $EnvFile -Key "VAULT_KV_MOUNT" -Value "secret"
Upsert-EnvValue -Path $EnvFile -Key "VAULT_KV_PATH" -Value "tradingagents/api-keys"
Upsert-EnvValue -Path $EnvFile -Key "VAULT_KEYS" -Value "GOOGLE_API_KEY,OPENROUTER_API_KEY"

Write-Host "Vault bootstrap completed successfully."
