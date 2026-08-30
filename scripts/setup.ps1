$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$sourcePython = if ($env:FORMULAWITNESS_PYTHON) {
    $env:FORMULAWITNESS_PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $sourcePython -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $venvPython -m pip install --no-deps -r (Join-Path $repoRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
& $venvPython -m pip install -e $repoRoot --no-deps --no-build-isolation
if ($LASTEXITCODE -ne 0) { throw 'ClauseGrid editable installation failed.' }
Write-Output "ClauseGrid environment ready: $venvPython"
