@echo off
REM ============================================================
REM  SPAM - Envoi du projet vers le depot GitHub (une seule fois)
REM  Depot : https://github.com/Arinaudo/SPAM
REM ============================================================
setlocal
cd /d "%~dp0"
title SPAM - Envoi vers GitHub

where git >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Git introuvable. Ouvre "Git Bash" ou installe Git for Windows.
    pause
    exit /b 1
)

echo === Preparation du depot local ===
if not exist ".git" git init
git branch -M main
git config user.email "rinaudo.alexis@gmail.com"
git config user.name "Arinaudo"

echo === Ajout des fichiers (hors .venv/build/dist grace au .gitignore) ===
git add .
git commit -m "SPAM - version initiale"

echo === Liaison au depot GitHub et envoi ===
git remote remove origin 2>nul
git remote add origin https://github.com/Arinaudo/SPAM.git
git push -u origin main

echo.
echo ============================================================
echo  Termine. Va sur GitHub (onglet Actions) pour lancer le build.
echo  Une fenetre de connexion GitHub a pu s'ouvrir : accepte-la.
echo ============================================================
pause
endlocal
