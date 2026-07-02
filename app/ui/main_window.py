"""
Fenetre principale : barre d'onglets (Composer, Destinataires, File d'attente,
Historique, Parametres) et etat partage (parametres, base, client Graph).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QStatusBar, QTabWidget, QWidget,
)

from ..config import APP_TITLE, APP_SUBTITLE, APP_VERSION, DB_PATH, TOKEN_CACHE_PATH, Settings
from ..core.database import Database
from ..core.graph_client import GraphClient
from .compose_tab import ComposeTab
from .recipients_tab import RecipientsTab
from .queue_tab import QueueTab
from .history_tab import HistoryTab
from .dashboard_tab import DashboardTab
from .delivery_tab import DeliveryTab
from .settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} — {APP_SUBTITLE}  (v{APP_VERSION})")
        self.resize(1100, 740)

        # Etat partage
        self.settings = Settings()
        self.db = Database(DB_PATH)
        self.graph = GraphClient(
            client_id=self.settings.get("client_id"),
            tenant_id=self.settings.get("tenant_id"),
            token_cache_path=TOKEN_CACHE_PATH,
        )

        # Donnees de travail partagees entre onglets
        self.recipients = []        # liste de dicts prepares
        self.recipients_source = ""  # nom du fichier importe

        # Onglets
        self.tabs = QTabWidget()
        self.compose_tab = ComposeTab(self)
        self.recipients_tab = RecipientsTab(self)
        self.queue_tab = QueueTab(self)
        self.history_tab = HistoryTab(self)
        self.dashboard_tab = DashboardTab(self)
        self.delivery_tab = DeliveryTab(self)
        self.settings_tab = SettingsTab(self)

        self.tabs.addTab(self.compose_tab, "1. Composer")
        self.tabs.addTab(self.recipients_tab, "2. Destinataires")
        self.tabs.addTab(self.queue_tab, "3. File d'attente")
        self.tabs.addTab(self.dashboard_tab, "Tableau de bord")
        self.tabs.addTab(self.history_tab, "Historique")
        self.tabs.addTab(self.delivery_tab, "Délivrabilité")
        self.tabs.addTab(self.settings_tab, "Paramètres")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        # Barre de statut : etat de connexion
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.account_label = QLabel()
        self.status.addPermanentWidget(self.account_label)
        self.refresh_account_status()

    # ------------------------------------------------------------------
    def refresh_account_status(self):
        info = None
        try:
            info = self.graph.signed_in_user()
        except Exception:
            info = None
        if info and info[1]:
            self.account_label.setText(f"  Connecté : {info[1]}  ")
            self.account_label.setStyleSheet("color: #176d2c; font-weight: bold;")
        else:
            self.account_label.setText("  Non connecté à Outlook  ")
            self.account_label.setStyleSheet("color: #b00020; font-weight: bold;")

    def rebuild_graph_client(self):
        """Recree le client Graph apres modification des parametres Azure."""
        self.graph = GraphClient(
            client_id=self.settings.get("client_id"),
            tenant_id=self.settings.get("tenant_id"),
            token_cache_path=TOKEN_CACHE_PATH,
        )
        self.refresh_account_status()

    def _on_tab_changed(self, index):
        w = self.tabs.widget(index)
        if hasattr(w, "on_show"):
            w.on_show()

    def closeEvent(self, event):
        if self.queue_tab.is_sending():
            r = QMessageBox.question(
                self, "Envoi en cours",
                "Un envoi est en cours. Quitter quand meme ?\n"
                "(La progression est sauvegardee et pourra etre reprise.)",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                event.ignore()
                return
            self.queue_tab.stop_sending(wait=True)
        try:
            self.queue_tab.keepawake.stop()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        event.accept()
