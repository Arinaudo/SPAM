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
    # Windows : déclarer une identité d'app propre pour que la barre des tâches
    # utilise NOTRE icône (sinon elle affiche celle de python.exe).
    if sys.platform.startswith("win"):
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
