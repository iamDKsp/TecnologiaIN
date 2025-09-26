param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir '..')
Push-Location $RepoRoot

try {
    Write-Host "Repo root:" $RepoRoot
    if (-not $SkipInstall) {
        Write-Host "Installing dependencies defined in requirements.txt..."
        python -m pip install --upgrade pip
        python -m pip install -r requirements.txt
    }

    Write-Host "Starting Flask development server..."
    python -m flask --app webapp.app run
}
finally {
    Pop-Location
}
