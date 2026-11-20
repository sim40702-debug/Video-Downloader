@echo off
rem ------------------------------------------------------------
rem install_windows.bat
rem Installa tutto quello che serve per Video Downloader su Windows.
rem Uso: doppio clic, oppure dal terminale: install_windows.bat
rem Si puo' rieseguire quando vuoi: aggiorna anche yt-dlp.
rem ------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo.
echo === Installazione di Video Downloader (Windows) ===
echo.

rem 1) Python 3.10 o piu' recente
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto manca_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 goto manca_python
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v

%PY% -c "import tkinter" 2>nul
if errorlevel 1 (
    echo [X] Manca tkinter. Reinstalla Python da python.org spuntando "tcl/tk and IDLE".
    goto fine_errore
)
echo [OK] tkinter presente

rem 2) Ambiente virtuale e librerie
if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente virtuale .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto fine_errore
)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
echo Installo/aggiorno le librerie (customtkinter, yt-dlp, pillow, requests)...
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt --quiet
if errorlevel 1 goto fine_errore
echo [OK] Librerie installate

rem 3) FFmpeg e Deno (con winget)
call :controlla_programma ffmpeg Gyan.FFmpeg
call :controlla_programma deno DenoLand.Deno

rem 4) Test veloci
echo Eseguo i test...
".venv\Scripts\python.exe" -m unittest discover -s tests -q
rem I test non devono lasciare file in giro
if exist __pycache__ rd /s /q __pycache__
if exist tests\__pycache__ rd /s /q tests\__pycache__

echo.
echo [OK] Installazione finita!
echo Per avviare l'app: doppio clic su "Avvia Video Downloader.bat"
echo Per compilare l'app .exe: build_windows.bat
echo.
if not "%~1"=="senza-pausa" pause
exit /b 0

rem ---- funzione: controlla un programma e se manca lo installa ----
:controlla_programma
where %1 >nul 2>nul
if not errorlevel 1 (
    echo [OK] %1 trovato
    exit /b 0
)
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\%1.exe" (
    echo [OK] %1 trovato
    exit /b 0
)
echo [!] %1 non trovato.
where winget >nul 2>nul
if errorlevel 1 (
    echo     Installa "App Installer" dal Microsoft Store, poi: winget install %2
    exit /b 0
)
choice /c SN /m "    Vuoi installare %1 adesso con winget"
if errorlevel 2 exit /b 0
winget install --id %2 -e --accept-source-agreements --accept-package-agreements
exit /b 0

:manca_python
echo [X] Serve Python 3.10 o piu' recente.
echo     Installalo con:  winget install Python.Python.3.12
echo     oppure da https://www.python.org (spunta "Add python.exe to PATH").
goto fine_errore

:fine_errore
echo.
echo Installazione non riuscita.
if not "%~1"=="senza-pausa" pause
exit /b 1
