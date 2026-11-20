@echo off
rem ------------------------------------------------------------
rem build_windows.bat
rem Compila l'app per Windows.
rem Risultato in dist\:
rem   - Video Downloader\Video Downloader.exe   (l'app)
rem   - Video-Downloader-windows.zip              (da caricare su Gitea)
rem ------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo === Compilazione di Video Downloader per Windows ===

if not exist ".venv\Scripts\python.exe" call install_windows.bat senza-pausa
if not exist ".venv\Scripts\python.exe" goto errore

echo Installo/aggiorno PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller --quiet

rem Puliamo eventuali build vecchie
if exist build_temp rd /s /q build_temp
if exist build rd /s /q build
if exist "dist\Video Downloader" rd /s /q "dist\Video Downloader"
if exist "dist\Video-Downloader-windows.zip" del /q "dist\Video-Downloader-windows.zip"
mkdir build_temp

rem Icona
".venv\Scripts\python.exe" crea_icona.py build_temp
if errorlevel 1 goto errore

echo Compilo con PyInstaller (ci vuole qualche minuto)...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --windowed ^
    --name "Video Downloader" ^
    --icon "%CD%\build_temp\icona.ico" ^
    --collect-all customtkinter ^
    --collect-all yt_dlp_ejs ^
    --collect-data certifi ^
    --workpath build_temp\work ^
    --specpath build_temp ^
    --distpath dist ^
    main.py
if errorlevel 1 goto errore

echo Creo lo zip per Gitea...
".venv\Scripts\python.exe" -c "import shutil; shutil.make_archive(r'dist\Video-Downloader-windows', 'zip', 'dist', 'Video Downloader')"
if errorlevel 1 goto errore

rem Pulizia dei file temporanei
if exist build_temp rd /s /q build_temp
if exist build rd /s /q build
if exist __pycache__ rd /s /q __pycache__

echo.
echo [OK] Fatto!
echo   App: dist\Video Downloader\Video Downloader.exe
echo   Zip: dist\Video-Downloader-windows.zip
echo.
echo Consiglio: copia la cartella "dist\Video Downloader" in
echo   %LOCALAPPDATA%\Programs\
echo e crea un collegamento al .exe sul Desktop. In quella cartella
echo l'app si puo' aggiornare da sola (in "Programmi" no, servono i permessi).
exit /b 0

:errore
echo.
echo [X] Compilazione non riuscita.
exit /b 1
