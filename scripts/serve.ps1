param(
  [Parameter(Mandatory = $true)][string]$Model,
  [string]$Provider = 'nvidia-nim',
  [switch]$AllowExternalProcessing
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
$modelArgs = @('-m', 'formulawitness', 'serve', '--host', '127.0.0.1', '--port', '8765', '--provider', $Provider, '--model', $Model)
if ($AllowExternalProcessing) { $modelArgs += '--allow-external-processing' }
Push-Location $repoRoot
try { & $pythonExe @modelArgs } finally { Pop-Location }
