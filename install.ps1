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
  Write-Host "  .\install.ps1"
  exit 1
}

if (Test-Path "packages/archivum-cli/src/index.js") {
  & node packages/archivum-cli/src/index.js install @InstallerArgs
} else {
  & npx --yes archivum install @InstallerArgs
}
