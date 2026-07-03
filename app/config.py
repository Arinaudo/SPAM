"""
SPAM - Systeme Pratique pour l'Automatisation des Mails
Configuration et gestion des donnees applicatives (cross-platform Windows/Mac).

Toutes les donnees persistantes (base SQLite, cache de connexion, parametres,
template HTML, images) sont stockees dans un dossier applicatif standard :
  - Windows : %APPDATA%/SPAM
  - macOS   : ~/Library/Application Support/SPAM
  - Linux   : ~/.local/share/SPAM
"""

import json
import os
import sys
from pathlib import Path

APP_NAME = "SPAM"
APP_TITLE = "SPAM"
APP_SUBTITLE = "Systeme Pratique pour l'Automatisation des Mails"
APP_VERSION = "1.0.0"


def app_data_dir() -> Path:
    """Dossier de donnees applicatif, cree s'il n'existe pas."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_dir() -> Path:
    """Dossier des ressources embarquees (template, logo par defaut).

    Gere le cas PyInstaller (sys._MEIPASS) et le cas execution depuis les sources.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        packaged = base / "app" / "resources"
        return packaged if packaged.exists() else base / "resources"
    return Path(__file__).resolve().parent / "resources"


DATA_DIR = app_data_dir()
DB_PATH = DATA_DIR / "spam_mailer.db"
TOKEN_CACHE_PATH = DATA_DIR / "token_cache.bin"
SETTINGS_PATH = DATA_DIR / "settings.json"
ASSETS_DIR = DATA_DIR / "assets"           # images importees par l'utilisateur
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# Parametres par defaut
# ----------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    # Microsoft Graph / Azure AD
    "client_id": "f569a610-c1c7-4afa-a677-351775f08615",
    "tenant_id": "common",
    # Cadence d'envoi (secondes entre deux mails)
    "delay_min": 5.0,
    "delay_max": 8.0,
    # Pause entre lots
    "batch_size": 100,
    "batch_pause_min": 60.0,
    "batch_pause_max": 120.0,
    # Contenu par defaut
    "default_subject": "Portefeuille Castignac : Actifs logistiques disponibles",
    # Salutations finales tirees au hasard (anti-spam)
    "closing_salutations": [
        "Bien a vous,",
        "Cordialement,",
        "Bien cordialement,",
        "Dans l'attente de votre retour,",
        "Au plaisir d'echanger prochainement,",
    ],
    "greeting_fallback": "Bonjour,",
    # Salutations d'ouverture selon la civilite (defaut, surchargeable par campagne)
    "greeting_monsieur": "Bonjour Monsieur,",
    "greeting_madame": "Bonjour Madame,",
    # Signature en bas du mail (defaut, surchargeable par campagne ;
    # une ligne = un saut de ligne. Laisser vide pour aucune signature)
    "signature_html": "",
    # Ajoute un en-tete unique x-mailing-ref par mail (variation d'empreinte)
    "add_invisible_ref": True,
    # Enregistre une copie dans les Elements envoyes Outlook
    "save_to_sent": True,
    # Empeche la mise en veille du PC pendant un envoi en cours
    "prevent_sleep": True,
}


class Settings:
    """Petit gestionnaire de parametres persistes en JSON."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = Path(path)
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Fusion : on garde les nouvelles cles par defaut si absentes
                for k, v in saved.items():
                    self._data[k] = v
            except Exception:
                pass
        return self

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def update(self, mapping: dict):
        self._data.update(mapping)

    def as_dict(self) -> dict:
        return dict(self._data)
