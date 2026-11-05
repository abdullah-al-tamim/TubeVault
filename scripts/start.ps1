$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m tubevault
if ($LASTEXITCODE -ne 0) { throw 'TubeVault stopped with an error. Run in a terminal to inspect startup errors.' }
