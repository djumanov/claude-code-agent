# DaVinci Resolve MCP - Windows o'rnatuvchi
# Ishga tushirish (repo papkasida):  powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $base = "py -3" } else { $base = "python" }
Write-Host "1/3 Virtual muhit yaratilmoqda (.venv)..."
Invoke-Expression "$base -m venv .venv"
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "2/3 Paketlar o'rnatilmoqda..."
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPy -m pip install -e .

Write-Host "3/3 Claude Desktop ga ulanmoqda..."
& $venvPy scripts\register_claude.py $venvPy

Write-Host ""
Write-Host "Tayyor! Endi:"
Write-Host " - DaVinci Resolve: Preferences > System > General > External scripting using = Local"
Write-Host " - Claude Desktop ni to'liq yopib qayta oching"
Write-Host " - Claude Code uchun:  claude mcp add davinci-resolve -- `"$venvPy`" -m davinci_resolve_mcp"
