@echo off
rem Dublu-click pe acest fisier porneste interfata de pontaj (Windows).
rem Prima data instaleaza ce lipseste (Playwright); apoi doar porneste.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Lipseste Python 3. Instaleaza-l de pe https://www.python.org/downloads/
  echo si bifeaza "Add python.exe to PATH" la instalare, apoi porneste din nou.
  pause
  exit /b 1
)

python -c "import playwright" >nul 2>nul
if errorlevel 1 (
  echo Instalez Playwright ^(o singura data^)...
  python -m pip install playwright || (echo Nu am putut instala Playwright. & pause & exit /b 1)
)

if not exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" if not exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" if not exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
  echo Google Chrome nu e instalat; descarc Chromium ^(o singura data^)...
  python -m playwright install chromium
)

echo Pornesc interfata. Inchide fereastra asta ca sa opresti serverul.
python gui.py
