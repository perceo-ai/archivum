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
  Write-Host "The Archivum CLI was not found at packages/archivum-cli/src/index.js." -ForegroundColor Yellow
  Write-Host "Run this from a full checkout: git clone https://github.com/perceo-ai/archivum.git"
  Write-Host "(The unscoped 'archivum' package on npm is not ours, so there is no npx fallback.)"
  exit 1
}
