$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$rootPath = $root.Path
$shellTabPath = $rootPath
$escapedRootPath = $rootPath.Replace("'", "''")
$escapedShellTabPath = $shellTabPath.Replace("'", "''")

$backCommand = "Set-Location -LiteralPath '$escapedRootPath'; npm run back"
$frontCommand = "Set-Location -LiteralPath '$escapedRootPath'; npm run front"
$shellCommand = "Set-Location -LiteralPath '$escapedShellTabPath'"
$encodedBackCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($backCommand))
$encodedFrontCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($frontCommand))
$encodedShellCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($shellCommand))

$windowsTerminal = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $windowsTerminal) {
    throw "Windows Terminal(wt.exe) was not found. Install Windows Terminal or run the front/back scripts manually."
}

& $windowsTerminal.Source `
    new-tab --title "greed-back" -d $rootPath powershell.exe -NoExit -ExecutionPolicy Bypass -EncodedCommand $encodedBackCommand `
    ";" `
    new-tab --title "greed-front" -d $rootPath powershell.exe -NoExit -ExecutionPolicy Bypass -EncodedCommand $encodedFrontCommand `
    ";" `
    new-tab --title "greed-shell" -d $shellTabPath powershell.exe -NoExit -ExecutionPolicy Bypass -EncodedCommand $encodedShellCommand
