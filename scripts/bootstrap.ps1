$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:ARCHIVUM_REPO_URL) { $env:ARCHIVUM_REPO_URL } else { "https://github.com/pranavkannepalli/archivum.git" }
$InstallDir = if ($env:ARCHIVUM_INSTALL_DIR) { $env:ARCHIVUM_INSTALL_DIR } else { Join-Path $HOME "archivum" }
$Branch = if ($env:ARCHIVUM_BRANCH) { $env:ARCHIVUM_BRANCH } else { "main" }
$RawBase = if ($env:ARCHIVUM_RAW_BASE) { $env:ARCHIVUM_RAW_BASE } else { "https://raw.githubusercontent.com/pranavkannepalli/archivum/$Branch" }
$FullClone = if ($env:ARCHIVUM_FULL_CLONE) { $env:ARCHIVUM_FULL_CLONE } else { "0" }

function Say($Message) {
  Write-Host $Message -ForegroundColor Cyan
}

function Warn($Message) {
  Write-Host $Message -ForegroundColor Yellow
}

function Need-Command($Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Say "Archivum one-command installer"

if ($FullClone -eq "1" -and -not (Need-Command git)) {
  if (Need-Command winget) {
    Say "Installing Git with winget."
    winget install --id Git.Git -e --source winget
  } else {
    throw "Git is required. Install it from https://git-scm.com/download/win and re-run this command."
  }
}

if (-not (Need-Command python) -and -not (Need-Command py)) {
  if (Need-Command winget) {
    Say "Installing Python with winget."
    winget install --id Python.Python.3.12 -e --source winget
  } else {
    throw "Python 3 is required. Install it from https://www.python.org/downloads/windows/ and re-run this command."
  }
}

$dockerReady = $false
if (Need-Command docker) {
  try {
    docker compose version | Out-Null
    docker info | Out-Null
    $dockerReady = $true
  } catch {
    $dockerReady = $false
  }
}

if (-not $dockerReady) {
  if (-not (Need-Command docker) -and (Need-Command winget)) {
    Say "Installing Docker Desktop with winget."
    winget install --id Docker.DockerDesktop -e --source winget
  }
  Warn "Start Docker Desktop and finish any WSL 2/reboot prompts, then re-run this command:"
  Warn '  irm https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.ps1 | iex'
  Start-Process "https://docs.docker.com/desktop/setup/install/windows-install/"
  exit 1
}

function Download-File($RemotePath, $LocalPath) {
  New-Item -ItemType Directory -Force -Path (Split-Path $LocalPath) | Out-Null
  Invoke-WebRequest -Uri "$RawBase/$RemotePath" -OutFile $LocalPath
}

if ($FullClone -eq "1") {
  if (Test-Path (Join-Path $InstallDir ".git")) {
    Say "Updating Archivum in $InstallDir"
    git -C $InstallDir fetch --all --prune
    git -C $InstallDir checkout $Branch
    git -C $InstallDir pull --ff-only
  } else {
    Say "Cloning Archivum into $InstallDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
    git clone --branch $Branch $RepoUrl $InstallDir
  }
} else {
  Say "Downloading minimal Archivum runtime files into $InstallDir"
  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Download-File ".env.example" (Join-Path $InstallDir ".env.example")
  Download-File "docker-compose.yml" (Join-Path $InstallDir "docker-compose.yml")
  Download-File "docker-compose.images.yml" (Join-Path $InstallDir "docker-compose.images.yml")
  Download-File "caddy/Caddyfile" (Join-Path $InstallDir "caddy/Caddyfile")
  Download-File "scripts/install.py" (Join-Path $InstallDir "scripts/install.py")
}

Set-Location $InstallDir
if (Need-Command py) {
  & py -3 scripts/install.py --images
} else {
  & python scripts/install.py --images
}
