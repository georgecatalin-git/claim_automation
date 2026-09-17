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

rem PYCMD e comanda cu care se porneste Python, exact cum se scrie in linie:
rem "py -3", "python", sau o cale cu ghilimele. Se foloseste mereu %PYCMD%,
rem fara alte ghilimele in jur: versiunea veche punea ghilimele peste
rem ghilimele si "py -3" devenea o comanda inexistenta ("pip nu merge").

rem ---------------------------------------------------------------- Python

echo.
echo == Python 3 (minim %PY_MIN_MAJOR%.%PY_MIN_MINOR%)
call :find_python
if not defined PYCMD (
  echo Nu am gasit un Python potrivit.
  call :install_python
  call :find_python
  if not defined PYCMD (
    echo Python s-a instalat, dar nu il gasesc inca. Inchide si deschide din nou fisierul.
    pause
    exit /b 1
  )
)
echo OK: Python !PYMAJ!.!PYMIN! (%PYCMD%)

rem ---------------------------------------------------------------- Actualizare
rem Imediat dupa Python, inainte de restul: asa un bug intr-un pas de mai
rem jos al lansatorului se repara singur la urmatoarea pornire.

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
%PYCMD% update.py
if exist "Pontaj.bat.new" (
  move /y "Pontaj.bat.new" "Pontaj.bat" >nul
  echo Lansatorul a fost actualizat; il pornesc din nou.
  call "Pontaj.bat"
  exit /b
)
if exist "Pontaj.command.new" del /q "Pontaj.command.new"

rem ---------------------------------------------------------------- pip

echo.
echo == pip
%PYCMD% -m pip --version >nul 2>nul || %PYCMD% -m ensurepip --user >nul 2>nul
%PYCMD% -m pip --version >nul 2>nul || %PYCMD% -m ensurepip >nul 2>nul
%PYCMD% -m pip --version >nul 2>nul || (
  echo pip nu merge cu acest Python. Reinstaleaza Python de pe python.org
  echo cu "pip" bifat la instalare, apoi porneste din nou.
  pause
  exit /b 1
)
echo OK

rem ---------------------------------------------------------------- Playwright

echo.
echo == Playwright
%PYCMD% -c "import playwright" >nul 2>nul
if errorlevel 1 (
  echo Instalez Playwright ^(o singura data^)...
  %PYCMD% -m pip install --user playwright >nul 2>nul || %PYCMD% -m pip install playwright || (echo Nu am putut instala Playwright. & pause & exit /b 1)
  %PYCMD% -c "import playwright" >nul 2>nul || (echo Playwright tot nu se incarca. & pause & exit /b 1)
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
      %PYCMD% -m playwright install chromium || (echo Nici Chromium nu s-a putut descarca. & pause & exit /b 1)
    )
  )
)

rem ---------------------------------------------------------------- Pornire

echo.
echo == Pornesc interfata
echo Inchide fereastra asta ca sa opresti serverul.
%PYCMD% gui.py
exit /b %errorlevel%

rem ================================================================ functii

:find_python
rem Candidatii, in ordine. 'python' din Microsoft Store e un stub care
rem deschide magazinul; il demasca faptul ca nu tipareste nimic.
set "PYCMD="
if not defined PYCMD call :check_python py -3
if not defined PYCMD call :check_python python
if not defined PYCMD call :check_python python3
if not defined PYCMD call :check_python "%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYCMD call :check_python "%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYCMD call :check_python "%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYCMD call :check_python "%LocalAppData%\Programs\Python\Python310\python.exe"
if not defined PYCMD call :check_python "%ProgramFiles%\Python313\python.exe"
if not defined PYCMD call :check_python "%ProgramFiles%\Python312\python.exe"
if not defined PYCMD call :check_python "%ProgramFiles%\Python311\python.exe"
exit /b 0

:check_python
rem Versiunea se citeste din sys.version_info, printr-un fisier temporar:
rem 'for /f' cu o comanda care are ghilimele in ea (o cale cu spatii) e
rem o capcana clasica a lui cmd, si asa a picat prima versiune.
set "CAND=%*"
set "PYVER_FILE=%TEMP%\pontaj-pyver.txt"
del /q "%PYVER_FILE%" >nul 2>nul
%CAND% -c "import sys; print(sys.version_info[0], sys.version_info[1])" > "%PYVER_FILE%" 2>nul
if not exist "%PYVER_FILE%" exit /b 0
set "PYVER="
set /p PYVER=<"%PYVER_FILE%"
del /q "%PYVER_FILE%" >nul 2>nul
if not defined PYVER exit /b 0
for /f "tokens=1,2" %%a in ("!PYVER!") do (
  set "MAJ=%%a"
  set "MIN=%%b"
)
if not defined MAJ exit /b 0
if !MAJ! GTR %PY_MIN_MAJOR% (set "PYCMD=%CAND%" & set "PYMAJ=!MAJ!" & set "PYMIN=!MIN!" & exit /b 0)
if !MAJ! EQU %PY_MIN_MAJOR% if !MIN! GEQ %PY_MIN_MINOR% (set "PYCMD=%CAND%" & set "PYMAJ=!MAJ!" & set "PYMIN=!MIN!")
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
