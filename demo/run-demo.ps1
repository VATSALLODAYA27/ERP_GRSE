<#
Starts the Drawing Compliance Checker demo as one process and opens it in the browser.

    .\demo\run-demo.ps1            keep earlier checks, decisions and comments (the normal way to run it)
    .\demo\run-demo.ps1 -Reset     start from an empty tool; the earlier data is moved to backend\var-archive, not deleted

It installs what is missing, loads the mock ERP files from demo\register, creates the users in
demo\demo_logins.json, builds the web app and serves everything on http://127.0.0.1:8000.
Press Ctrl+C to stop.
#>
param(
    [switch]$Reset,
    [int]$Port = 8000,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$url = "http://127.0.0.1:$Port"

function Step {
    param([string]$What, [scriptblock]$Command)
    Write-Host "== $What" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE) { throw "$What failed." }
}

if (-not (Test-Path $python)) {
    Step 'Creating the Python environment' { python -m venv (Join-Path $backend '.venv') }
    Step 'Installing backend packages' { & $python -m pip install --quiet -r (Join-Path $backend 'requirements.txt') }
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Step 'Installing web app packages' { npm --prefix $frontend install --silent }
}

$var = Join-Path $backend 'var'
if ($Reset -and (Test-Path $var)) {
    $archive = Join-Path $backend ('var-archive\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Write-Host "== Moving earlier checks, decisions and audit log to $archive" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force (Split-Path $archive -Parent) | Out-Null
    Move-Item $var $archive
}

Push-Location $backend
try {
    Step 'Loading the mock ERP register from demo\register' { & $python -m scripts.load_extract }
    Step 'Creating the demo users from demo\demo_logins.json' { & $python -m scripts.seed_users }
    Step 'Approving the demo rules (first run only)' { & $python -m scripts.approve_demo_rules }
    Step 'Building the web app' { npm --prefix $frontend run build --silent }

    Write-Host "== Starting the demo on $url  (Ctrl+C to stop)" -ForegroundColor Green
    $server = Start-Process -FilePath $python -ArgumentList '-m', 'uvicorn', 'app.main:app', '--port', $Port -NoNewWindow -PassThru
    try {
        # Open the browser only once the server answers, so the first page is not an error.
        foreach ($attempt in 1..30) {
            if ($server.HasExited) { throw 'The server stopped while starting. Read the error above.' }
            try { Invoke-WebRequest -UseBasicParsing "$url/api/auth/me" | Out-Null } catch {
                if ($_.Exception.Response) { break }  # any HTTP answer, even "not signed in", means it is up
                Start-Sleep -Milliseconds 500
            }
        }
        if (-not $NoBrowser) { Start-Process $url }
        Wait-Process -Id $server.Id
    }
    finally {
        if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    }
}
finally {
    Pop-Location
}
