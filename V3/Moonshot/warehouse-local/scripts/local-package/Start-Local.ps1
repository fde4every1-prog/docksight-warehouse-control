[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Local environment not found. Run .\Setup-Local.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $Root "local_server.py") -PathType Leaf)) {
    throw "local_server.py is missing from the package root."
}
if (-not (Test-Path -LiteralPath (Join-Path $Root ".env") -PathType Leaf)) {
    throw ".env is missing. Run .\Setup-Local.ps1 first."
}

Set-Location -LiteralPath $Root
$Port = if ($env:PORT) { $env:PORT } else { "8080" }
Write-Host "Starting at http://127.0.0.1:$Port"
& $Python (Join-Path $Root "local_server.py")
exit $LASTEXITCODE