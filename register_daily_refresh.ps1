param(
    [string]$Time = "02:30"
)

$ErrorActionPreference = "Stop"

if ($Time -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') {
    throw "Time must use 24-hour HH:mm format, for example 02:30."
}

$projectDir = (Resolve-Path $PSScriptRoot).Path
$entryPoint = Join-Path $projectDir "daily_refresh.py"
$python = (& python -c "import sys; print(sys.executable)").Trim()
$taskName = "OCHA Sanctions Daily Refresh"
$startTime = [datetime]::ParseExact(
    $Time,
    "HH:mm",
    [Globalization.CultureInfo]::InvariantCulture
)

if (-not (Test-Path $entryPoint)) {
    throw "Refresh entry point not found: $entryPoint"
}
if (-not (Test-Path $python)) {
    throw "Python executable not found: $python"
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$entryPoint`"" `
    -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $startTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Refresh configured OCHA sanctions and ineligibility feeds daily." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $taskName
