#!/bin/bash
# ============================================================
#  SPAM - Construction de l'application macOS
#  Genere dist/SPAM.app
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[1/3] Creation de l'environnement virtuel..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "[2/3] Installation des dependances..."
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo "[3/3] Construction de l'application..."
pyinstaller --noconfirm --clean \
    --name "SPAM" \
    --windowed \
    --onefile \
    --icon "app/resources/icon.icns" \
    --add-data "app/resources:app/resources" \
    main.py

echo ""
echo "============================================================"
echo " Termine. L'application se trouve dans : dist/SPAM.app"
echo " (Au 1er lancement : clic droit > Ouvrir, pour contourner Gatekeeper.)"
echo "============================================================"
