$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "backend"
$frontend = Join-Path $repoRoot "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found. Create it and install backend\.[dev] first."
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Copy-Item (Join-Path $backend ".env.example") (Join-Path $backend ".env")
    throw "Created backend\.env from the example. Set PostgreSQL credentials and unique signing keys, then rerun."
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run npm install in frontend first."
}

Push-Location $backend
try {
    & $python -m flask --app wsgi config-check
    if ($LASTEXITCODE -ne 0) { throw "Backend configuration check failed." }
    & $python -m flask --app wsgi db-check
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL connectivity check failed." }
    & $python -m flask --app wsgi db upgrade
    if ($LASTEXITCODE -ne 0) { throw "Database migrations failed." }
    & $python -m flask --app wsgi seed-demo-catalog --apply --confirm-local-database
    if ($LASTEXITCODE -ne 0) { throw "Demo catalog seeding failed." }
    & $python -m flask --app wsgi dev-provision-admin
    if ($LASTEXITCODE -ne 0) { throw "Local administrator provisioning failed." }
}
finally {
    Pop-Location
}

$api = Start-Process -FilePath $python `
    -ArgumentList @("run.py") `
    -WorkingDirectory $backend `
    -PassThru `
    -NoNewWindow

try {
    Write-Host "Starting MemoryBook API at http://127.0.0.1:5000 and Vite at http://127.0.0.1:5173."
    Push-Location $frontend
    npm run dev -- --host 127.0.0.1
    if ($LASTEXITCODE -ne 0) { throw "Vite exited with an error." }
}
finally {
    Pop-Location
    if (-not $api.HasExited) {
        Stop-Process -Id $api.Id
        Wait-Process -Id $api.Id -ErrorAction SilentlyContinue
    }
}
