$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$ruffExe = Join-Path $repoRoot '.venv\Scripts\ruff.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
Push-Location $repoRoot
try {
    & $ruffExe format --check .
    & $ruffExe check .
    & $pythonExe -m pytest -q
    & $pythonExe 'scripts\validate_benchmark.py' --root . --output 'artifacts\benchmark-validation.json'
    & $pythonExe -m formulawitness eval --output 'evals\results.json'
} finally {
    Pop-Location
}
