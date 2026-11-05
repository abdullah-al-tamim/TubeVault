$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or newer with the Python launcher first.' }
}
& .\.venv\Scripts\python.exe -m pip install -e '.[test]'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed.' }
} finally { Pop-Location }
New-Item -ItemType Directory -Force data | Out-Null
if (-not (Test-Path '.env')) {
    $secure = Read-Host 'Choose a vault password (at least 16 characters)' -AsSecureString
    $passwordText = [System.Net.NetworkCredential]::new('', $secure).Password
    if ($passwordText.Length -lt 16 -or $passwordText.Contains('"') -or $passwordText.Contains('`')) {
        throw 'Use at least 16 characters without double quotes or backticks.'
    }
    $template = Get-Content -LiteralPath '.env.example' -Raw
    $template.Replace('TUBEVAULT_PASSWORD=', 'TUBEVAULT_PASSWORD="' + $passwordText + '"') | Set-Content -LiteralPath '.env' -Encoding utf8
    $passwordText = $null
}
& .\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
Write-Host 'Setup complete. Run scripts\start.ps1, then open http://127.0.0.1:8765.'
