# ExamTrack one-click stopper.
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot

$pidFile = Join-Path $PSScriptRoot ".examtrack-server.pid"

if (Test-Path $pidFile) {
    $serverPid = Get-Content $pidFile | Select-Object -First 1
    if ($serverPid) {
        Stop-Process -Id $serverPid -Force
        Remove-Item $pidFile -Force
        Write-Host "Stopped ExamTrack website (PID $serverPid)."
    }
}

# Also catch a Flask process started by an older version of the launcher.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*flask*--app*app*run*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Stop only the MySQL instance that uses this project's data folder.
Get-CimInstance Win32_Process -Filter "Name='mysqld.exe'" |
    Where-Object { $_.CommandLine -like "*ExamTrack-MySQL*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "ExamTrack and its MySQL server have been stopped."
