#!/bin/bash
# Dublu-click pe acest fisier porneste interfata de pontaj (macOS).
# Prima data instaleaza ce lipseste (Playwright); apoi doar porneste.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Lipseste Python 3. Instaleaza-l de pe https://www.python.org/downloads/ si porneste din nou."
  read -r -p "Enter ca sa inchizi..."
  exit 1
fi

if ! python3 -c "import playwright" >/dev/null 2>&1; then
  echo "Instalez Playwright (o singura data)..."
  python3 -m pip install --user playwright || python3 -m pip install playwright || {
    echo "Nu am putut instala Playwright."; read -r -p "Enter ca sa inchizi..."; exit 1; }
fi

# Google Chrome e folosit daca exista (passkey / Touch ID); altfel Chromium.
if [ ! -d "/Applications/Google Chrome.app" ] && ! python3 -c "
import sys, pathlib
p = pathlib.Path.home() / 'Library/Caches/ms-playwright'
sys.exit(0 if any(p.glob('chromium-*')) else 1)
" >/dev/null 2>&1; then
  echo "Google Chrome nu e instalat; descarc Chromium (o singura data)..."
  python3 -m playwright install chromium
fi

echo "Pornesc interfata. Inchide fereastra asta ca sa opresti serverul."
python3 gui.py
