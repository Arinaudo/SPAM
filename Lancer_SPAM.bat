@echo off
REM ============================================================
REM  SPAM - Lanceur (cache vide a chaque lancement + journal)
REM  Double-cliquer sur ce fichier.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title SPAM - Lanceur
set LOG=%~dp0run_log.txt
echo ====== Demarrage %date% %time% ====== > "%LOG%"

REM --- 1) Trouver Python ------------------------------------
set PYEXE=
where py >nul 2>&1 && set PYEXE=py
if "!PYEXE!"=="" ( where python >nul 2>&1 && set PYEXE=python )
if "!PYEXE!"=="" (
    echo [PROBLEME] Python n'est pas installe. >> "%LOG%"
    echo Python n'est pas installe. Voir https://www.python.org/downloads/ ^(coche "Add Python to PATH"^).
    pause & exit /b 1
)

REM --- 2) Environnement virtuel ----------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Premiere preparation ^(quelques minutes^)...
    !PYEXE! -m venv .venv >> "%LOG%" 2>&1
)
set VPY=.venv\Scripts\python.exe

REM --- 3) Dependances --------------------------------------
"%VPY%" -c "import PySide6, msal, requests, pandas, openpyxl, dns.resolver" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo Installation des dependances ^(quelques minutes^)...
    "%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
    "%VPY%" -m pip install -r requirements.txt >> "%LOG%" 2>&1
)

REM --- 4) Vider le cache de bytecode (force le code a jour) -
echo Nettoyage du cache... >> "%LOG%"
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

REM --- 5) Diagnostic : quel gabarit l'app lit-elle ? -------
echo ------ Diagnostic gabarit ------ >> "%LOG%"
"%VPY%" -B -c "from app.config import resource_dir; p=resource_dir()/'default_template.html'; t=p.read_text(encoding='utf-8'); print('TEMPLATE:',p); print('HAS_SIGNATURE_PLACEHOLDER:', '__SIGNATURE__' in t); print('HAS_OLD_HARDCODED:', 'Immobilier logistique' in t)" >> "%LOG%" 2>&1

REM --- 6) Lancer l'application (sans ecrire de .pyc) -------
echo Lancement... & echo ------ main.py ------ >> "%LOG%"
"%VPY%" -B main.py >> "%LOG%" 2>&1
set CODE=!errorlevel!
echo ------ Code de sortie : !CODE! ------ >> "%LOG%"
if not "!CODE!"=="0" (
    echo.
    echo [ERREUR] Fermeture anormale ^(code !CODE!^). Detail dans run_log.txt
    pause
)
endlocal
