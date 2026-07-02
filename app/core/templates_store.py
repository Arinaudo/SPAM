"""
Stockage des modèles de mail réutilisables (JSON persistant).

Un modèle = {subject, body_html, images, greetings, closings, signature}.
Les images sont un dict {cid: chemin} ; les fichiers eux-mêmes restent dans
ASSETS_DIR (persistant), donc on ne stocke que les chemins.
"""

import json

from ..config import DATA_DIR

TEMPLATES_PATH = DATA_DIR / "templates.json"


def load_templates() -> dict:
    if TEMPLATES_PATH.exists():
        try:
            with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _write(data: dict):
    with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_template(name: str, template: dict):
    data = load_templates()
    data[name] = template
    _write(data)


def delete_template(name: str):
    data = load_templates()
    data.pop(name, None)
    _write(data)


def get_template(name: str):
    return load_templates().get(name)


def template_names():
    return sorted(load_templates().keys())
