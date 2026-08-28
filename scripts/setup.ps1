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
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$repoRoot[dev]"
Write-Output "FormulaWitness environment ready: $venvPython"
