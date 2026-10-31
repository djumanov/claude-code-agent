#!/usr/bin/env bash
# Ikki marta bosing (birinchi marta: o'ng tugma > Open).
cd "$(dirname "$0")"
if [ ! -x /Library/Frameworks/Python.framework/Versions/Current/bin/python3 ] && ! command -v python3 >/dev/null; then
  echo "Python topilmadi. python.org dan macOS installer ni o'rnating va qayta ishga tushiring."
  open "https://www.python.org/downloads/macos/"
  read -r -p "Enter ni bosing..."
  exit 1
fi
bash scripts/install_mac.sh
read -r -p "Tayyor. Oynani yopish uchun Enter ni bosing..."
