"""
Fenetre principale : barre d'onglets (Composer, Destinataires, File d'attente,
Historique, Parametres) et etat partage (parametres, base, client Graph).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from . import theme

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
from .help_tab import HelpTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} — {APP_SUBTITLE}  (v{APP_VERSION})")
        self.setMinimumSize(860, 480)
        self.resize(1080, 680)

        # Etat partage
        self.settings = Settings()
        # Theme applique AVANT la construction des onglets (les couleurs
        # secondaires sont figees au demarrage).
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, self.settings.get("theme", "dark"))
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
        self.help_tab = HelpTab(self)

        self.tabs.addTab(self.help_tab, "Mode d'emploi")
        self.tabs.addTab(self.compose_tab, "1. Composer")
        self.tabs.addTab(self.recipients_tab, "2. Destinataires")
        self.tabs.addTab(self.delivery_tab, "3. Anti-spam")
        self.tabs.addTab(self.queue_tab, "4. Envoi")
        self.tabs.addTab(self.dashboard_tab, "Tableau de bord")
        self.tabs.addTab(self.history_tab, "Historique")
        self.tabs.addTab(self.settings_tab, "Paramètres")
        # Bulles d'aide en langage simple sur chaque onglet
        tips = {
            self.help_tab: "Comment utiliser l'application, pas a pas.",
            self.compose_tab: "Ecrire le mail : objet, texte, images, pieces jointes.",
            self.recipients_tab: "Importer et verifier la liste des destinataires.",
            self.delivery_tab: "Verifier que vos mails ne finissent pas en spam.",
            self.queue_tab: "Lancer l'envoi et suivre la progression.",
            self.dashboard_tab: "Vue d'ensemble des resultats.",
            self.history_tab: "Tous les mails envoyes : ouvertures, reponses, echecs.",
            self.settings_tab: "Connexion Outlook, apparence et options.",
        }
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w in tips:
                self.tabs.setTabToolTip(i, tips[w])
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Bandeau de connexion (visible seulement si non connecte a Outlook)
        self.connect_banner = self._build_connect_banner()

        central = QWidget()
        clay = QVBoxLayout(central)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(0)
        clay.addWidget(self.connect_banner)
        clay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # Barre de statut : etat de connexion
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.account_label = QLabel()
        self.status.addPermanentWidget(self.account_label)
        self.refresh_account_status()

    # ------------------------------------------------------------------
    def _build_connect_banner(self):
        """Bandeau d'invite a la connexion, masque quand on est connecte."""
        banner = QWidget()
        banner.setStyleSheet("background-color:#8a5a00;")   # orange sobre, lisible
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(12, 6, 12, 6)
        lbl = QLabel("Vous n'êtes pas connecté à Outlook. Connectez-vous pour pouvoir envoyer.")
        lbl.setStyleSheet("color:#ffffff; font-weight:bold;")
        lay.addWidget(lbl, 1)
        b = QPushButton("Se connecter")
        b.clicked.connect(self.connect_outlook)
        lay.addWidget(b)
        banner.hide()
        return banner

    def connect_outlook(self):
        """Connexion interactive a Outlook (depuis le bandeau)."""
        try:
            self.graph.get_token_interactive()
        except Exception as e:
            QMessageBox.critical(self, "Connexion", f"Échec de connexion :\n{e}")
            return
        self.refresh_account_status()
        try:
            self.settings_tab._refresh_status()
        except Exception:
            pass

    def refresh_account_status(self):
        info = None
        try:
            info = self.graph.signed_in_user()
        except Exception:
            info = None
        connected = bool(info and info[1])
        if connected:
            self.account_label.setText(f"  Connecté : {info[1]}  ")
            self.account_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.account_label.setText("  Non connecté à Outlook  ")
            self.account_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")
        if hasattr(self, "connect_banner"):
            self.connect_banner.setVisible(not connected)

    def rebuild_graph_client(self):
        """Recree le client Graph apres modification des parametres Azure."""
        self.graph = GraphClient(
            client_id=self.settings.get("client_id"),
            tenant_id=self.settings.get("tenant_id"),
            token_cache_path=TOKEN_CACHE_PATH,
        )
        self.refresh_account_status()

    def goto_help_target(self, key):
        """Navigue vers un onglet depuis un lien du Mode d'emploi.

        key : 'settings', 'compose', 'compose_write', 'recipients', 'queue',
        'history', 'dashboard', 'delivery'. Le suffixe '_write' place en plus
        le curseur dans la zone de redaction du Composer.
        """
        mapping = {
            "settings": self.settings_tab,
            "compose": self.compose_tab,
            "compose_write": self.compose_tab,
            "recipients": self.recipients_tab,
            "queue": self.queue_tab,
            "history": self.history_tab,
            "dashboard": self.dashboard_tab,
            "delivery": self.delivery_tab,
        }
        w = mapping.get(key)
        if w is None:
            return
        self.tabs.setCurrentWidget(w)
        if key == "compose_write" and hasattr(w, "focus_compose"):
            w.focus_compose()

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
