param(
  [switch]$Help,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$InstallerArgs
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if ($Help) {
  Write-Host "Runs the Archivum interactive installer."
  Write-Host "Usage: .\install.ps1"
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
  Write-Host "  .\install.ps1"
  exit 1
}

if ($python -eq "py") {
  & py -3 scripts/install.py @InstallerArgs
} else {
  & $python scripts/install.py @InstallerArgs
}
