"""
Theme de l'application : mode sombre (par defaut) ou clair.

- apply(app, mode) applique un style Fusion + une palette Qt coherente. La
  palette pilote la quasi-totalite de l'interface (fonds, textes, boutons,
  tableaux), donc tout ce qui n'impose pas de couleur en dur suit le theme.
- Des helpers de couleurs (hint / muted / accent / danger) sont fournis pour
  les rares textes qui ont besoin d'une couleur explicite (indications
  secondaires, titres colores). Ils renvoient une valeur adaptee au mode
  courant, fixe au demarrage (le changement de theme demande un redemarrage).
"""

from PySide6.QtGui import QColor, QPalette

_MODE = "dark"

# Palettes de couleurs secondaires par mode.
_COLORS = {
    "dark": {
        "hint": "#9AA0A6",     # indications discretes
        "muted": "#B8BDC2",    # texte secondaire un peu plus clair
        "accent": "#5AA9FF",   # titres / liens
        "danger": "#FF6B6B",   # erreurs
        "ok": "#5CD6A0",       # succes
    },
    "light": {
        "hint": "#666666",
        "muted": "#555555",
        "accent": "#0563C1",
        "danger": "#B00020",
        "ok": "#1E874B",
    },
}


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#232629"))
    p.setColor(QPalette.WindowText, QColor("#EAEAEA"))
    p.setColor(QPalette.Base, QColor("#1B1D1F"))
    p.setColor(QPalette.AlternateBase, QColor("#26292C"))
    p.setColor(QPalette.ToolTipBase, QColor("#2B2E31"))
    p.setColor(QPalette.ToolTipText, QColor("#EAEAEA"))
    p.setColor(QPalette.Text, QColor("#EAEAEA"))
    p.setColor(QPalette.Button, QColor("#2B2E31"))
    p.setColor(QPalette.ButtonText, QColor("#EAEAEA"))
    p.setColor(QPalette.BrightText, QColor("#FF5555"))
    p.setColor(QPalette.Link, QColor("#5AA9FF"))
    p.setColor(QPalette.Highlight, QColor("#2E6DA4"))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.PlaceholderText, QColor("#8A9096"))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#787D82"))
    return p


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#F2F2F2"))
    p.setColor(QPalette.WindowText, QColor("#1A1A1A"))
    p.setColor(QPalette.Base, QColor("#FFFFFF"))
    p.setColor(QPalette.AlternateBase, QColor("#F0F0F0"))
    p.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    p.setColor(QPalette.ToolTipText, QColor("#1A1A1A"))
    p.setColor(QPalette.Text, QColor("#1A1A1A"))
    p.setColor(QPalette.Button, QColor("#E6E6E6"))
    p.setColor(QPalette.ButtonText, QColor("#1A1A1A"))
    p.setColor(QPalette.BrightText, QColor("#B00020"))
    p.setColor(QPalette.Link, QColor("#0563C1"))
    p.setColor(QPalette.Highlight, QColor("#2E6DA4"))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.PlaceholderText, QColor("#888888"))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#9A9A9A"))
    return p


def apply(app, mode):
    """Applique le theme a l'application (style Fusion + palette)."""
    global _MODE
    _MODE = "light" if str(mode).lower() == "light" else "dark"
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    app.setPalette(_dark_palette() if _MODE == "dark" else _light_palette())


def mode() -> str:
    return _MODE


def is_dark() -> bool:
    return _MODE == "dark"


def color(name: str) -> str:
    """Couleur secondaire (hex) adaptee au mode courant."""
    return _COLORS[_MODE].get(name, "#888888")


def hint() -> str:
    return color("hint")


def muted() -> str:
    return color("muted")


def accent() -> str:
    return color("accent")


def danger() -> str:
    return color("danger")


def hint_css() -> str:
    return f"color:{hint()};"
