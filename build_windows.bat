@echo off
REM ============================================================
REM  SPAM - Construction de l'executable Windows
REM  Genere dist\SPAM.exe (un seul fichier a double-cliquer)
REM ============================================================
setlocal

cd /d "%~dp0"

echo [1/3] Creation de l'environnement virtuel...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/3] Installation des dependances...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [3/3] Construction de l'executable...
pyinstaller --noconfirm --clean ^
    --name "SPAM" ^
    --windowed ^
    --onefile ^
    --icon "app\resources\icon.ico" ^
    --add-data "app\resources;app/resources" ^
    main.py

echo.
echo ============================================================
echo  Termine. L'executable se trouve dans : dist\SPAM.exe
echo ============================================================
pause
