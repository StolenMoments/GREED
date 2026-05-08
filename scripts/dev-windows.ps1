$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$rootPath = $root.Path
$escapedRootPath = $rootPath.Replace("'", "''")

$backCommand = "Set-Location -LiteralPath '$escapedRootPath'; npm run back"
$frontCommand = "Set-Location -LiteralPath '$escapedRootPath'; npm run front"

Start-Process -FilePath "powershell.exe" `
    -WorkingDirectory $rootPath `
    -WindowStyle Normal `
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backCommand)

Start-Process -FilePath "powershell.exe" `
    -WorkingDirectory $rootPath `
    -WindowStyle Normal `
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontCommand)
