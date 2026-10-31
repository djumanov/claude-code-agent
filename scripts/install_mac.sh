#!/usr/bin/env bash
# DaVinci Resolve MCP - macOS/Linux o'rnatuvchi
# Ishga tushirish (repo papkasida):  bash scripts/install_mac.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "1/3 Virtual muhit yaratilmoqda (.venv)..."
python3 -m venv .venv
VENV_PY="$ROOT/.venv/bin/python"

echo "2/3 Paketlar o'rnatilmoqda..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -e .

echo "3/3 Claude Desktop ga ulanmoqda..."
"$VENV_PY" scripts/register_claude.py "$VENV_PY"

cat <<MSG

Tayyor! Endi:
 - DaVinci Resolve: Preferences > System > General > External scripting using = Local
 - Claude Desktop ni to'liq yopib (Cmd+Q) qayta oching
 - Claude Code uchun:  claude mcp add davinci-resolve -- "$VENV_PY" -m davinci_resolve_mcp
MSG
