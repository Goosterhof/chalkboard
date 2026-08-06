# install-task.ps1 — registers Chalkboard's refresh cycle in Windows Task Scheduler.
#
# Pins the working directory and points at the venv's pythonw.exe so the
# scheduled run never resolves config.json/output paths relative to
# Task Scheduler's default C:\Windows\System32 cwd, and never flashes a
# console window.
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot "config.json"
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$intervalMinutes = $config.refresh_minutes

$pythonw = Join-Path $repoRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    throw "pythonw.exe not found at $pythonw — run 'python -m venv .venv' then '.venv\Scripts\pip install -r requirements.txt' first."
}

$scriptPath = Join-Path $repoRoot "render_wallpaper.py"

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$scriptPath`"" -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $intervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -DontStopOnIdleEnd -StartWhenAvailable

Register-ScheduledTask -TaskName "Chalkboard" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Refreshes the Chalkboard live GitHub dashboard wallpaper." -Force

Write-Host "Registered scheduled task 'Chalkboard' — refreshing every $intervalMinutes minute(s) from $repoRoot."
