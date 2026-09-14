@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Dublu-click pe acest fisier porneste interfata de pontaj (Windows).
rem
rem Verifica, in ordine, ce ii trebuie aplicatiei si instaleaza ce lipseste:
rem   1. Python 3.9+   - winget daca exista, altfel instalatorul oficial python.org
rem   2. Playwright    - pip
rem   3. Google Chrome - winget daca exista, altfel instalatorul oficial Google;
rem                      fara el se foloseste Chromium-ul lui Playwright, unde
rem                      login-ul merge doar cu parola, nu cu passkey
rem Apoi porneste gui.py. Dupa prima data, verificarile trec intr-o secunda.

cd /d "%~dp0"

set "PY_MIN_MAJOR=3"
set "PY_MIN_MINOR=9"
set "PY_VERSION=3.12.7"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"
set "CHROME_URL=https://dl.google.com/chrome/install/latest/chrome_installer.exe"

rem ---------------------------------------------------------------- Python

echo.
echo == Python 3 (minim %PY_MIN_MAJOR%.%PY_MIN_MINOR%)
call :find_python
if not defined PY (
  echo Nu am gasit un Python potrivit.
  call :install_python
  call :find_python
  if not defined PY (
    echo Python s-a instalat, dar nu il gasesc inca. Inchide si deschide din nou fisierul.
    pause
    exit /b 1
  )
)
for /f "tokens=2" %%v in ('"%PY%" --version 2^>^&1') do echo OK: Python %%v (%PY%)

rem ---------------------------------------------------------------- pip

echo.
echo == pip
"%PY%" -m pip --version >nul 2>nul || "%PY%" -m ensurepip --user >nul 2>nul
"%PY%" -m pip --version >nul 2>nul || (echo pip nu merge cu acest Python. & pause & exit /b 1)
echo OK

rem ---------------------------------------------------------------- Playwright

echo.
echo == Playwright
"%PY%" -c "import playwright" >nul 2>nul
if errorlevel 1 (
  echo Instalez Playwright ^(o singura data^)...
  "%PY%" -m pip install --user playwright >nul 2>nul || "%PY%" -m pip install playwright || (echo Nu am putut instala Playwright. & pause & exit /b 1)
  "%PY%" -c "import playwright" >nul 2>nul || (echo Playwright tot nu se incarca. & pause & exit /b 1)
)
echo OK: instalat

rem ---------------------------------------------------------------- Google Chrome

echo.
echo == Google Chrome (pentru login cu passkey)
call :chrome_present
if "!CHROME!"=="1" (
  echo OK: instalat
) else (
  echo Google Chrome lipseste.
  call :install_chrome
  call :chrome_present
  if "!CHROME!"=="1" (
    echo OK: instalat
  ) else (
    echo Nu am putut instala Chrome; login-ul va merge doar cu parola, in Chromium.
    if not exist "%LocalAppData%\ms-playwright\chromium-*" (
      echo Descarc Chromium-ul lui Playwright ^(o singura data^)...
      "%PY%" -m playwright install chromium || (echo Nici Chromium nu s-a putut descarca. & pause & exit /b 1)
    )
  )
)

rem ---------------------------------------------------------------- Actualizare

echo.
echo == Actualizari
rem Un .bat nu se poate rescrie in timp ce ruleaza: versiunea noua sta in
rem Pontaj.bat.new si o punem la loc aici, apoi pornim din nou.
if exist "Pontaj.bat.new" (
  move /y "Pontaj.bat.new" "Pontaj.bat" >nul
  echo Lansatorul a fost actualizat; il pornesc din nou.
  call "Pontaj.bat"
  exit /b
)
"%PY%" update.py
if exist "Pontaj.bat.new" (
  move /y "Pontaj.bat.new" "Pontaj.bat" >nul
  echo Lansatorul a fost actualizat; il pornesc din nou.
  call "Pontaj.bat"
  exit /b
)
if exist "Pontaj.command.new" del /q "Pontaj.command.new"

rem ---------------------------------------------------------------- Pornire

echo.
echo == Pornesc interfata
echo Inchide fereastra asta ca sa opresti serverul.
"%PY%" gui.py
exit /b %errorlevel%

rem ================================================================ functii

:find_python
rem 'python' din Microsoft Store e un stub care deschide magazinul; il
rem demasca faptul ca '--version' nu tipareste nimic. Versiunea >= 3.9.
set "PY="
for %%c in ("py -3" "python" "python3" "%LocalAppData%\Programs\Python\Python313\python.exe" "%LocalAppData%\Programs\Python\Python312\python.exe" "%LocalAppData%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe") do (
  if not defined PY call :check_python %%c
)
exit /b 0

:check_python
set "CAND=%*"
for /f "tokens=2 delims=. " %%a in ('%CAND% --version 2^>nul') do set "MAJ=%%a"
for /f "tokens=3 delims=. " %%b in ('%CAND% --version 2^>nul') do set "MIN=%%b"
if not defined MAJ exit /b 0
if !MAJ! GTR %PY_MIN_MAJOR% (set "PY=%CAND%" & exit /b 0)
if !MAJ! EQU %PY_MIN_MAJOR% if !MIN! GEQ %PY_MIN_MINOR% set "PY=%CAND%"
set "MAJ=" & set "MIN="
exit /b 0

:install_python
where winget >nul 2>nul
if not errorlevel 1 (
  echo Instalez Python prin winget...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements && exit /b 0
  echo winget nu a reusit; incerc instalatorul oficial.
)
echo Descarc instalatorul oficial Python %PY_VERSION% ^(python.org^)...
set "PYEXE=%TEMP%\python-%PY_VERSION%.exe"
curl -fsSL -o "%PYEXE%" "%PY_URL%" || (echo Descarcarea a esuat. & exit /b 1)
echo Instalez Python ^(pentru utilizatorul curent, cu PATH^)...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
del /q "%PYEXE%" >nul 2>nul
exit /b 0

:chrome_present
set "CHROME=0"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=1"
exit /b 0

:install_chrome
where winget >nul 2>nul
if not errorlevel 1 (
  echo Instalez Google Chrome prin winget...
  winget install --id Google.Chrome -e --silent --accept-package-agreements --accept-source-agreements && exit /b 0
  echo winget nu a reusit; incerc instalatorul oficial.
)
echo Descarc Google Chrome ^(instalatorul oficial^)...
set "CHREXE=%TEMP%\chrome_installer.exe"
curl -fsSL -o "%CHREXE%" "%CHROME_URL%" || (echo Descarcarea a esuat. & exit /b 1)
"%CHREXE%" /silent /install
del /q "%CHREXE%" >nul 2>nul
exit /b 0
