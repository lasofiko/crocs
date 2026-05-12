#Requires -Version 5.0
<#
.SYNOPSIS
    Запуск пайплайна crocs (прогноз + опционально расписание).

.DESCRIPTION
    Переходит в каталог репозитория, при наличии .venv использует его Python,
    вызывает: python -u -m crocs <ваши аргументы> (-u = небуферизованный вывод, heartbeat сразу виден).

.EXAMPLE
    .\run.ps1
    .\run.ps1 --check-only
    .\run.ps1 --data-dir data/raw --artifacts-dir artifacts --config configs/default.yaml
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPy) { $venvPy } else { "python" }

Write-Host "CWD: $ProjectRoot" -ForegroundColor DarkGray
Write-Host "Python: $python" -ForegroundColor DarkGray

& $python -u -m crocs @args
exit $LASTEXITCODE
