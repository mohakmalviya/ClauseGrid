$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$ruffExe = Join-Path $repoRoot '.venv\Scripts\ruff.exe'
$pytestTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("formulawitness-pytest-" + [guid]::NewGuid().ToString('N'))
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
Push-Location $repoRoot
try {
    & $ruffExe format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }
    & $ruffExe check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }
    & $pythonExe -m mypy
    if ($LASTEXITCODE -ne 0) { throw 'Mypy failed.' }
    # OneDrive may hold directory handles long enough to break pytest's base-temp cleanup.
    & $pythonExe -m pytest -q --basetemp $pytestTemp -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Pytest failed.' }
    & $pythonExe 'scripts\validate_benchmark.py' --root . --output 'artifacts\benchmark-validation.json'
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark mutation validation failed.' }
    & $pythonExe -m formulawitness eval --output 'evals\results.json'
    if ($LASTEXITCODE -ne 0) { throw 'Frozen evaluation failed.' }
    & $pythonExe -m formulawitness verify-trajectory 'trajectories\baseline-m10.jsonl'
    if ($LASTEXITCODE -ne 0) { throw 'Baseline trajectory verification failed.' }
    & $pythonExe -m formulawitness verify-trajectory 'trajectories\advanced-m10.jsonl'
    if ($LASTEXITCODE -ne 0) { throw 'Advanced trajectory verification failed.' }
    $generatedHash = (Get-FileHash -LiteralPath 'evals\results.json' -Algorithm SHA256).Hash
    $submittedHash = (Get-FileHash -LiteralPath 'artifacts\submission\evaluation-results.json' -Algorithm SHA256).Hash
    if ($generatedHash -ne $submittedHash) {
        throw 'Submitted evaluation result does not match a fresh frozen evaluation.'
    }
} finally {
    Pop-Location
}
