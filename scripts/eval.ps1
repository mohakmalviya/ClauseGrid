$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
Push-Location $repoRoot
try { & $pythonExe -m formulawitness eval --output 'evals\results.json' } finally { Pop-Location }
