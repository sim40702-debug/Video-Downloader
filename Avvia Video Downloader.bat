@echo off
rem Doppio clic su questo file per avviare Video Downloader su Windows.
rem La prima volta installa automaticamente tutto quello che serve.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" call install_windows.bat senza-pausa
if not exist ".venv\Scripts\pythonw.exe" (
    echo Installazione non riuscita.
    pause
    exit /b 1
)
rem pythonw apre la finestra dell'app senza la finestra nera del terminale
start "" ".venv\Scripts\pythonw.exe" main.py
