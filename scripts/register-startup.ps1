param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$taskName = 'TubeVault Local Archive'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    return
}
$projectDir = (Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
$pythonPath = Join-Path $projectDir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 first.' }
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument '-m tubevault' -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Local TubeVault archive; current Windows user credential store.' -Force | Out-Null
Write-Host 'Registered at sign-in for the current user. No administrator account or stored Windows password is needed.'
