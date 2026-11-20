@echo off
rem ------------------------------------------------------------
rem rilascia.bat  (PC Windows)
rem Aggiunge la versione Windows alla release su Gitea.
rem
rem Prima lancia sul Mac:  ./rilascia.sh 1.0.1 "note"
rem Poi qui:               rilascia.bat
rem
rem 1. scarica le ultime modifiche da GitHub (con la nuova versione)
rem 2. compila l'app per Windows
rem 3. carica lo zip nella release su Gitea
rem ------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo 1) Scarico le ultime modifiche da GitHub...
git pull --no-rebase --no-edit
if errorlevel 1 goto errore

echo 2) Compilo l'app per Windows...
call build_windows.bat
if errorlevel 1 goto errore

echo 3) Carico su Gitea...
".venv\Scripts\python.exe" pubblica_release.py %1
if errorlevel 1 goto errore

echo.
echo [OK] Rilascio Windows completato.
pause
exit /b 0

:errore
echo.
echo [X] Rilascio non riuscito.
pause
exit /b 1
