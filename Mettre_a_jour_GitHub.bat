@echo off
REM ============================================================
REM  SPAM - Envoie les corrections sur GitHub et declenche une
REM  reconstruction (Windows + Mac) via un nouveau tag.
REM ============================================================
setlocal
cd /d "%~dp0"
title SPAM - Mise a jour GitHub

REM Retire le mail sensible du depot (loyers)
if exist "mail_portefeuille.html" del /q "mail_portefeuille.html"

git config user.email "rinaudo.alexis@gmail.com"
git config user.name "Arinaudo"

echo === Envoi des corrections ===
git add -A
git commit -m "Corrections : icone barre des taches, mise en page Mac, chemin ressources"
git push -f origin main

echo === Nouveau tag v1.0.2 (declenche la reconstruction) ===
git tag v1.0.2
git push origin v1.0.2

echo.
echo ============================================================
echo  Termine. La reconstruction demarre sur GitHub (~5 min).
echo  Ensuite les liens ...releases/latest/download/SPAM.exe et
echo  SPAM.dmg serviront les versions corrigees.
echo ============================================================
pause
endlocal
