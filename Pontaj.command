#!/bin/bash
# Dublu-click pe acest fisier porneste interfata de pontaj (macOS).
#
# Verifica, in ordine, ce ii trebuie aplicatiei si instaleaza ce lipseste:
#   1. Python 3.9+   - Homebrew daca exista, altfel instalatorul de pe python.org
#   2. Playwright    - pip
#   3. Google Chrome - Homebrew daca exista, altfel dmg-ul oficial Google;
#                      fara el se foloseste Chromium-ul lui Playwright, unde
#                      login-ul merge doar cu parola, nu cu passkey
# Apoi porneste gui.py. Dupa prima data, verificarile trec intr-o secunda.

cd "$(dirname "$0")" || exit 1

PY_MIN_MAJOR=3
PY_MIN_MINOR=9
PY_PKG_VERSION="3.12.7"
PY_PKG_URL="https://www.python.org/ftp/python/${PY_PKG_VERSION}/python-${PY_PKG_VERSION}-macos11.pkg"
CHROME_DMG_URL="https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg"

# Instalatoarele nu pot schimba PATH-ul shell-ului deja pornit, asa ca
# locurile cunoscute se pun aici de mana.
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

pause_exit() {
  echo
  read -r -p "Enter ca sa inchizi..."
  exit "${1:-1}"
}

step() { echo; echo "== $1"; }

# ---------------------------------------------------------------- Python

python_ok() {
  # Stub-ul Apple 'python3' fara Command Line Tools deschide un dialog si
  # iese cu eroare; '--version' il demasca. Versiunea trebuie sa fie >= 3.9.
  local v
  v="$("$1" --version 2>/dev/null | awk '{print $2}')" || return 1
  [ -n "$v" ] || return 1
  local major minor
  major="${v%%.*}"; minor="${v#*.}"; minor="${minor%%.*}"
  [ "$major" -gt "$PY_MIN_MAJOR" ] 2>/dev/null && return 0
  [ "$major" -eq "$PY_MIN_MAJOR" ] && [ "$minor" -ge "$PY_MIN_MINOR" ] 2>/dev/null
}

find_python() {
  local c
  for c in python3 python3.13 python3.12 python3.11 python3.10 python3.9 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
           /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && python_ok "$c"; then
      echo "$c"; return 0
    fi
  done
  return 1
}

install_python() {
  if command -v brew >/dev/null 2>&1; then
    echo "Instalez Python prin Homebrew..."
    brew install python@3.12 && return 0
    echo "Homebrew nu a reusit; incerc instalatorul oficial."
  fi
  echo "Descarc instalatorul oficial Python ${PY_PKG_VERSION} (python.org)..."
  local pkg="/tmp/python-${PY_PKG_VERSION}.pkg"
  curl -fsSL -o "$pkg" "$PY_PKG_URL" || { echo "Descarcarea a esuat."; return 1; }
  echo "Instalarea cere parola calculatorului (sudo):"
  sudo installer -pkg "$pkg" -target / || return 1
  rm -f "$pkg"
}

step "Python 3 (minim ${PY_MIN_MAJOR}.${PY_MIN_MINOR})"
PY="$(find_python)" || {
  echo "Nu am gasit un Python potrivit."
  install_python || {
    echo "Nu am putut instala Python. Instaleaza-l de pe https://www.python.org/downloads/ si porneste din nou."
    pause_exit
  }
  PY="$(find_python)" || { echo "Python s-a instalat, dar nu il gasesc. Inchide si deschide din nou fisierul."; pause_exit; }
}
echo "OK: $("$PY" --version) ($PY)"

# ---------------------------------------------------------------- pip

step "pip"
if ! "$PY" -m pip --version >/dev/null 2>&1; then
  echo "pip lipseste; il pornesc..."
  "$PY" -m ensurepip --user >/dev/null 2>&1 || "$PY" -m ensurepip >/dev/null 2>&1
fi
"$PY" -m pip --version >/dev/null 2>&1 && echo "OK: $("$PY" -m pip --version | awk '{print $1, $2}')" || {
  echo "pip nu merge cu acest Python."; pause_exit; }

# ---------------------------------------------------------------- Playwright

step "Playwright"
if "$PY" -c "import playwright" >/dev/null 2>&1; then
  echo "OK: instalat"
else
  echo "Instalez Playwright (o singura data)..."
  "$PY" -m pip install --user playwright >/dev/null 2>&1 || "$PY" -m pip install playwright || {
    echo "Nu am putut instala Playwright."; pause_exit; }
  "$PY" -c "import playwright" >/dev/null 2>&1 && echo "OK: instalat" || { echo "Playwright tot nu se incarca."; pause_exit; }
fi

# ---------------------------------------------------------------- Google Chrome

step "Google Chrome (pentru login cu passkey / Touch ID)"
install_chrome() {
  if command -v brew >/dev/null 2>&1; then
    echo "Instalez Google Chrome prin Homebrew..."
    brew install --cask google-chrome && return 0
    echo "Homebrew nu a reusit; incerc dmg-ul oficial."
  fi
  echo "Descarc Google Chrome (dmg oficial)..."
  local dmg="/tmp/googlechrome.dmg" mnt
  curl -fsSL -o "$dmg" "$CHROME_DMG_URL" || { echo "Descarcarea a esuat."; return 1; }
  mnt="$(hdiutil attach -nobrowse -readonly "$dmg" 2>/dev/null | awk -F'\t' '/\/Volumes\//{print $NF; exit}')"
  [ -n "$mnt" ] || { echo "Nu am putut monta dmg-ul."; return 1; }
  if ! cp -R "$mnt/Google Chrome.app" /Applications/ 2>/dev/null; then
    echo "Copierea in /Applications cere parola calculatorului (sudo):"
    sudo cp -R "$mnt/Google Chrome.app" /Applications/ || { hdiutil detach "$mnt" >/dev/null 2>&1; return 1; }
  fi
  hdiutil detach "$mnt" >/dev/null 2>&1
  rm -f "$dmg"
}
if [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]; then
  echo "OK: instalat"
else
  echo "Google Chrome lipseste."
  if install_chrome; then
    echo "OK: instalat"
  else
    echo "Nu am putut instala Chrome; login-ul va merge doar cu parola, in Chromium."
    if ! ls "$HOME/Library/Caches/ms-playwright"/chromium-* >/dev/null 2>&1; then
      echo "Descarc Chromium-ul lui Playwright (o singura data)..."
      "$PY" -m playwright install chromium || { echo "Nici Chromium nu s-a putut descarca."; pause_exit; }
    fi
  fi
fi

# ---------------------------------------------------------------- Actualizare

step "Actualizari"
# Daca lansatorul insusi a fost actualizat data trecuta, il punem la loc
# acum, inainte sa mearga mai departe (un script bash nu se poate rescrie
# in timp ce ruleaza).
if [ -f "Pontaj.command.new" ]; then
  mv -f "Pontaj.command.new" "Pontaj.command" && chmod +x "Pontaj.command"
  echo "Lansatorul a fost actualizat; il pornesc din nou."
  exec bash "Pontaj.command"
fi
"$PY" update.py
if [ -f "Pontaj.command.new" ]; then
  mv -f "Pontaj.command.new" "Pontaj.command" && chmod +x "Pontaj.command"
  echo "Lansatorul a fost actualizat; il pornesc din nou."
  exec bash "Pontaj.command"
fi
rm -f "Pontaj.bat.new"

step "Pornesc interfata"
echo "Inchide fereastra asta ca sa opresti serverul."
"$PY" gui.py
