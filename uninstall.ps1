param(
  [switch]$Help,
  [switch]$Volumes,
  [switch]$Images,
  [switch]$Files,
  [switch]$Yes,
  [switch]$DryRun,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$UninstallerArgs
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if ($Help) {
  Write-Host "Runs the Archivum uninstaller."
  Write-Host "Usage: .\uninstall.ps1 [-Volumes] [-Images] [-Files] [-Yes] [-DryRun]"
  exit 0
}

$node = $null
foreach ($candidate in @("node")) {
  $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
  if ($cmd) {
    $node = $candidate
    break
  }
}

if (-not $node) {
  Write-Host "Node.js 20 or newer was not found." -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Install Node.js from:"
  Write-Host "  https://nodejs.org/"
  Write-Host ""
  Write-Host "Then re-run:"
  Write-Host "  .\uninstall.ps1"
  exit 1
}

$argsForPython = @()
if ($Volumes) { $argsForPython += "--volumes" }
if ($Images) { $argsForPython += "--images" }
if ($Files) { $argsForPython += "--files" }
if ($Yes) { $argsForPython += "--yes" }
if ($DryRun) { $argsForPython += "--dry-run" }
if ($UninstallerArgs) { $argsForPython += $UninstallerArgs }

if (Test-Path "packages/archivum-cli/src/index.js") {
  & node packages/archivum-cli/src/index.js uninstall @argsForPython
} else {
  & npx --yes archivum uninstall @argsForPython
}
