[CmdletBinding()]
param(
    [switch]$InstallBuildTools
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

$EnvPath = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
    @"
OPENAI_API_KEY=sk-dummy-replace-with-your-own-key
OPENAI_BASE_URL=https://api.openai.com/v1
"@ | Set-Content -LiteralPath $EnvPath -Encoding ascii
    Write-Host "Created .env with a non-secret dummy OpenAI key."
}

try {
    $Version = & py -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
} catch {
    throw "Python 3.11 was not found. Install 64-bit Python 3.11, including the py launcher, then retry."
}
if ($LASTEXITCODE -ne 0 -or $Version.Trim() -ne "3.11") {
    throw "Python 3.11 was not found. Install 64-bit Python 3.11, including the py launcher, then retry."
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe" -PathType Leaf)) {
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install Python requirements." }

if ($InstallBuildTools) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Optional rebuilding requires Node.js 22. Install it and rerun with -InstallBuildTools."
    }
    $NodeVersion = (& node --version)
    if ($LASTEXITCODE -ne 0 -or -not $NodeVersion -or $NodeVersion -notmatch '^v22\.') {
        throw "Optional rebuilding requires Node.js 22. Installed version: $NodeVersion"
    }
    & npm.cmd install --global pnpm@10.26.1
    if ($LASTEXITCODE -ne 0) { throw "Could not install pnpm 10.26.1." }
    Write-Host "Build tools ready: Node $NodeVersion, pnpm $(& pnpm --version)"
}

Write-Host "Setup complete. Node.js is not required to run the bundled prebuilt applications."
Write-Host "Core apps run with the dummy .env value; AI suggestions require your own key in .env."
Write-Host "Start with: .\Start-Local.ps1"