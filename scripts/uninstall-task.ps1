# uninstall-task.ps1 — removes Chalkboard's scheduled refresh cycle.
$ErrorActionPreference = "Stop"

Unregister-ScheduledTask -TaskName "Chalkboard" -Confirm:$false
Write-Host "Unregistered scheduled task 'Chalkboard'. The last chalked wallpaper stays put until you change it."
