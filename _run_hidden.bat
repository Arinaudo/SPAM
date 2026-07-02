@echo off
REM ============================================================
REM  SPAM - execution interne (appele par SPAM.vbs, fenetre cachee)
REM  Ne pas double-cliquer directement : utiliser SPAM.vbs
REM ============================================================
cd /d "%~dp0"

REM Si l'environnement n'existe pas, on delegue au lanceur visible
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0Lancer_SPAM.bat"
    exit /b
)

REM Dependances manquantes (ex. dnspython) -> installation via lanceur visible
".venv\Scripts\python.exe" -c "import PySide6, msal, requests, pandas, openpyxl, dns.resolver" 2>nul
if errorlevel 1 (
    call "%~dp0Lancer_SPAM.bat"
    exit /b
)

REM Vide le cache de bytecode (force le code a jour)
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

REM Lance l'application ; toute sortie/erreur va dans run_log.txt
".venv\Scripts\python.exe" -B main.py > "%~dp0run_log.txt" 2>&1
