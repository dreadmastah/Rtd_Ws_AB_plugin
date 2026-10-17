param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Runtime,
    [Parameter(Mandatory=$true)][string]$Python
)
$ErrorActionPreference = 'Stop'
$taskName = 'WSRTD PR3 Test Supervisor Watchdog'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Runtime = (Resolve-Path -LiteralPath $Runtime).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
foreach ($file in @((Join-Path $Root 'Binance\sender.py'),
                    (Join-Path $Root 'Relay\Server\Python\relay.py'),
                    (Join-Path $Runtime 'selected-symbols.txt'))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing test file: $file" }
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Task already exists; inspect it before changing it: $taskName"
}
$installedScript = Join-Path $Runtime 'supervise_test_feed.py'
if (Test-Path -LiteralPath $installedScript) {
    throw "Supervisor installation file already exists: $installedScript"
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'supervise_test_feed.py') -Destination $installedScript
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArguments = '-u -B "{0}" --root "{1}" --runtime "{2}"' -f $installedScript,$Root,$Runtime
$action = New-ScheduledTaskAction -Execute $Python -Argument $actionArguments -WorkingDirectory $Root
$periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($periodic,$logon) -Settings $settings -Principal $principal -Description 'Owns only the isolated WSRTD PR3 port 18101 feed. Respects its STOP file. No production or Broker process control.' | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $Runtime 'watchdog-task.xml') -Encoding utf8
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
