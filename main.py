"""
CMA - Castignac Mailing App
Point d'entree de l'application de bureau.

Lancement depuis les sources :
    python main.py
"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import APP_TITLE, resource_dir
from app.ui.main_window import MainWindow


def main():
    # Windows : ce réglage d'identité n'est utile QUE lancé depuis python.exe
    # (pour que la barre des tâches n'affiche pas l'icône de Python). Sur le
    # .exe packagé, on le SAUTE : l'icône embarquée dans le .exe sert alors
    # directement d'icône de barre des tâches (sinon Windows montre le défaut).
    if sys.platform.startswith("win") and not getattr(sys, "frozen", False):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Castignac.SPAM.Mailer")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    icon_path = resource_dir() / "icon.png"
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)
    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
