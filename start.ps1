# ExamTrack one-click launcher.
# Double-click START.bat instead of running this file manually.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$mysqlBase = "C:\Program Files\MySQL\MySQL Server 8.4"
$mysqld = Join-Path $mysqlBase "bin\mysqld.exe"
$mysqlClient = Join-Path $mysqlBase "bin\mysql.exe"
$mysqlData = Join-Path $env:USERPROFILE "ExamTrack-MySQL\Data"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pidFile = Join-Path $PSScriptRoot ".examtrack-server.pid"
$logFile = Join-Path $PSScriptRoot "examtrack-server.log"
$errorLogFile = Join-Path $PSScriptRoot "examtrack-server-error.log"
$appUrl = "http://127.0.0.1:5000"

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Read-EnvValue([string]$Key) {
    $line = Get-Content (Join-Path $PSScriptRoot ".env") -ErrorAction SilentlyContinue |
        Where-Object { $_ -match ("^" + [regex]::Escape($Key) + "=(.*)$") } | Select-Object -First 1
    if ($line -and $line -match "=") { return $line.Substring($line.IndexOf("=") + 1).Trim() }
    return ""
}

function Invoke-Quiet([string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $File @Arguments 2>$null | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

Write-Host ""
Write-Host "  ===================================================" -ForegroundColor Cyan
Write-Host "   ExamTrack - Examination & Result Management" -ForegroundColor Cyan
Write-Host "  ===================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $python)) {
    Write-Host "[1/5] First run: creating Python environment..." -ForegroundColor Yellow
    python -m venv .venv
    if (-not (Test-Path $python)) { throw "Python 3.12 was not found. Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'." }
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -r requirements.txt
} else {
    Write-Host "[1/5] Python environment ready."
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Write-Host "[2/5] First run: creating configuration..." -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $PSScriptRoot ".env")
    $secret = & $python -c "import secrets; print(secrets.token_hex(32))"
    $envPath = Join-Path $PSScriptRoot ".env"
    $content = Get-Content $envPath -Raw
    $content = $content.Replace("replace-with-a-long-random-secret-key", $secret)
    $content = $content.Replace("MYSQL_USER=root", "MYSQL_USER=esrms_user")
    $dbPw = & $python -c "import secrets; print(secrets.token_urlsafe(18))"
    $rootPw = & $python -c "import secrets; print(secrets.token_urlsafe(18))"
    $content = $content.Replace("MYSQL_PASSWORD=your-mysql-password", "MYSQL_PASSWORD=" + $dbPw)
    $content += "`nMYSQL_ROOT_PASSWORD=" + $rootPw + "`n"
    Set-Content -Path $envPath -Value $content -Encoding UTF8
} else {
    Write-Host "[2/5] Configuration ready."
}

if (-not (Test-Path $mysqld)) {
    throw "MySQL Server 8.4 was not found at '$mysqld'. Install MySQL Server 8.4 from https://dev.mysql.com/downloads/mysql/."
}

if (-not (Test-Path $mysqlData)) {
    Write-Host "[3/5] First run: initialising MySQL data folder..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $mysqlData | Out-Null
    & $mysqld --initialize-insecure --basedir=$mysqlBase --datadir=$mysqlData | Out-Null
} else {
    Write-Host "[3/5] MySQL data folder ready."
}

if (-not (Test-Port 3306)) {
    Write-Host "      Starting MySQL server..." -ForegroundColor Yellow
    $mysqlArgs = "--basedir=`"$mysqlBase`" --datadir=`"$mysqlData`" --port=3306 --bind-address=127.0.0.1 --console"
    Start-Process -FilePath $mysqld -ArgumentList $mysqlArgs `
        -WorkingDirectory (Join-Path $mysqlBase "bin") -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Port 3306) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Port 3306)) {
        throw "MySQL did not start. Check '$mysqlData' and the MySQL error log (*.err)."
    }

    $rootPw = Read-EnvValue "MYSQL_ROOT_PASSWORD"
    $dbPw = Read-EnvValue "MYSQL_PASSWORD"
    $sql = "CREATE DATABASE IF NOT EXISTS esrms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; " +
           "CREATE USER IF NOT EXISTS 'esrms_user'@'localhost' IDENTIFIED BY '" + $dbPw + "'; " +
           "GRANT ALL PRIVILEGES ON esrms.* TO 'esrms_user'@'localhost'; FLUSH PRIVILEGES;"
    $setupCode = Invoke-Quiet $mysqlClient @("-u", "root", "-p$rootPw", "-h", "127.0.0.1", "-e", $sql)
    if ($setupCode -ne 0) {
        $setupSql = "ALTER USER 'root'@'localhost' IDENTIFIED BY '" + $rootPw + "'; " + $sql
        Invoke-Quiet $mysqlClient @("-u", "root", "-h", "127.0.0.1", "-e", $setupSql) | Out-Null
    }
}
Write-Host "      MySQL is running."

Write-Host "[4/5] Preparing database tables and demo data..."
if ((Invoke-Quiet $python @("-m", "flask", "--app", "app", "init-db")) -ne 0) {
    throw "Could not create database tables. Run 'python -m flask --app app init-db' manually to see the error."
}
if ((Invoke-Quiet $python @("-m", "flask", "--app", "app", "seed", "--demo")) -ne 0) {
    throw "Could not seed demo data. Run 'python -m flask --app app seed --demo' manually to see the error."
}

if (-not (Test-Port 5000)) {
    Write-Host "[5/5] Starting website..." -ForegroundColor Yellow
    $proc = Start-Process -FilePath $python -ArgumentList @(
        "-m", "flask", "--app", "app", "run", "--host", "127.0.0.1", "--port", "5000", "--no-debug"
    ) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $logFile -RedirectStandardError $errorLogFile
    Set-Content -Path $pidFile -Value $proc.Id

    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Port 5000) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 400 }
    if (-not (Test-Port 5000)) {
        throw "Website did not start. Check '$logFile'."
    }
} else {
    Write-Host "[5/5] Website is already running."
}

# One-time desktop shortcut so the project is always one double-click away.
try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "ExamTrack.lnk"
    if (-not (Test-Path $shortcutPath)) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        try {
            $fso = New-Object -ComObject Scripting.FileSystemObject
            $shortRoot = $fso.GetFolder($PSScriptRoot).ShortPath
        } catch {
            $shortRoot = $PSScriptRoot
        }
        $shortcut.TargetPath = (Join-Path $shortRoot "START.bat")
        $shortcut.WorkingDirectory = $shortRoot
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
        $shortcut.Description = "Launch the ExamTrack website"
        $shortcut.Save()
        Write-Host "      Desktop shortcut 'ExamTrack' created."
    }
} catch {
    # Shortcut creation is a convenience only; never fail startup because of it.
}

Start-Process $appUrl

Write-Host ""
Write-Host "  ExamTrack is open at $appUrl" -ForegroundColor Green
Write-Host "  Admin: admin / Admin@123" -ForegroundColor Green
Write-Host "  Student: student1 / Student@123" -ForegroundColor Green
Write-Host ""
Write-Host "  To stop everything, double-click STOP.bat (or run stop.ps1)." -ForegroundColor DarkGray
Write-Host ""
