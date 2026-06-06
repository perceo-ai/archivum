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

$python = $null
foreach ($candidate in @("py", "python", "python3")) {
  $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
  if ($cmd) {
    $python = $candidate
    break
  }
}

if (-not $python) {
  Write-Host "Python 3 was not found." -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Install Python 3 from:"
  Write-Host "  https://www.python.org/downloads/windows/"
  Write-Host ""
  Write-Host "During install, check 'Add python.exe to PATH'. Then re-run:"
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

if ($python -eq "py") {
  & py -3 scripts/uninstall.py @argsForPython
} else {
  & $python scripts/uninstall.py @argsForPython
}
