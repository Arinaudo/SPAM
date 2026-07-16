"""
Onglet Historique : liste de tous les mails traites (envoyes / en erreur),
toutes campagnes confondues, avec recherche, filtre par statut et export CSV.
"""

import csv
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core import tracking, replies, bounces

COLS = ["Date", "Email", "Nom", "Société", "Statut", "Ouvertures", "Réponses",
        "Campagne", "Objet", "Erreur"]


def _reply_display(reply_type, reply_count):
    """Libelle de la colonne Réponses selon le type et le nombre."""
    rt = reply_type or ""
    rc = int(reply_count or 0)
    if rt == "human":
        return "Oui" if rc <= 1 else f"Oui ({rc})"
    if rt == "auto":
        return "Auto"
    return "—"


class HistoryTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        root = QVBoxLayout(inner)

        top = QHBoxLayout()
        top.addWidget(QLabel("Rechercher :"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("email, nom, société, objet...")
        self.search.returnPressed.connect(self.reload)
        top.addWidget(self.search, 1)
        top.addWidget(QLabel("Statut :"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("Tous", "")
        self.status_filter.addItem("Envoyés", "sent")
        self.status_filter.addItem("Erreurs", "error")
        self.status_filter.currentIndexChanged.connect(self.reload)
        top.addWidget(self.status_filter)
        b_reload = QPushButton("Actualiser")
        b_reload.clicked.connect(self.reload)
        top.addWidget(b_reload)
        b_opens = QPushButton("Rafraîchir les ouvertures")
        b_opens.setToolTip("Récupère les ouvertures depuis le tracker et met à jour la colonne Ouvertures.")
        b_opens.clicked.connect(self.refresh_opens)
        top.addWidget(b_opens)
        b_replies = QPushButton("Rafraîchir les réponses")
        b_replies.setToolTip("Lit la boîte Outlook et met à jour la colonne Réponses.")
        b_replies.clicked.connect(self.refresh_replies)
        top.addWidget(b_replies)
        b_bounces = QPushButton("Rafraîchir les bounces")
        b_bounces.setToolTip("Lit les rapports de non-remise (NDR) et met les adresses "
                             "mortes en liste de suppression + statut invalide.")
        b_bounces.clicked.connect(self.refresh_bounces)
        top.addWidget(b_bounces)
        b_export = QPushButton("Exporter CSV")
        b_export.clicked.connect(self.export_csv)
        top.addWidget(b_export)
        root.addLayout(top)

        self.count_label = QLabel("")
        root.addWidget(self.count_label)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

    def on_show(self):
        self.reload()

    def reload(self):
        search = self.search.text().strip()
        status = self.status_filter.currentData()
        self._rows = self.mw.db.history(search=search, status_filter=status, limit=5000)
        self.count_label.setText(f"{len(self._rows)} entrée(s)")
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            oc = int(r.get("open_count", 0) or 0)
            opened = "—" if oc == 0 else (f"Oui ({oc})" if oc > 1 else "Oui")
            rtype = r.get("reply_type", "") or ""
            reply_disp = _reply_display(rtype, r.get("reply_count", 0))
            vals = [r.get("sent_at", ""), r.get("email", ""), r.get("nom", ""),
                    r.get("societe", ""), r.get("status", ""), opened, reply_disp,
                    r.get("campaign", ""), r.get("subject", ""), r.get("error", "")]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 4 and r.get("status") == "error":
                    item.setForeground(Qt.red)
                if j == 5 and oc > 0:
                    item.setForeground(Qt.darkGreen)
                if j == 6 and rtype == "human":
                    item.setForeground(Qt.darkGreen)
                if j == 6 and rtype == "auto":
                    item.setForeground(Qt.darkYellow)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

    def refresh_opens(self):
        """Recupere les ouvertures depuis le tracker et met a jour la base."""
        s = self.mw.settings
        if not s.get("tracking_enabled", False):
            QMessageBox.information(
                self, "Suivi d'ouverture",
                "Le suivi d'ouverture n'est pas activé.\n"
                "Active-le dans les paramètres (URL du tracker + clé).")
            return
        base_url = (s.get("tracking_base_url", "") or "").strip()
        api_key = (s.get("tracking_api_key", "") or "").strip()
        if not base_url:
            QMessageBox.warning(self, "Suivi d'ouverture",
                                "URL du tracker non renseignée dans les paramètres.")
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            records = tracking.fetch_opens(base_url, api_key)
            updated = self.mw.db.apply_opens(records)
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Suivi d'ouverture",
                                 f"Échec de la récupération :\n{e}")
            return
        QGuiApplication.restoreOverrideCursor()
        self.reload()
        QMessageBox.information(
            self, "Suivi d'ouverture",
            f"{len(records)} mail(s) ouvert(s) au total.\n"
            f"{updated} destinataire(s) mis à jour dans l'historique.")

    def _since_from_earliest(self):
        """Borne ISO UTC calculee depuis le plus ancien envoi (marge 1 jour), ou None."""
        earliest = self.mw.db.earliest_sent_at()  # 'YYYY-mm-dd HH:MM:SS' (local)
        if earliest:
            try:
                dt = datetime.datetime.strptime(earliest, "%Y-%m-%d %H:%M:%S")
                # naive -> local -> UTC, avec 1 jour de marge de securite
                dt_utc = dt.astimezone().astimezone(datetime.timezone.utc)
                dt_utc -= datetime.timedelta(days=1)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                return None
        return None

    def _reply_since(self):
        """Borne de temps (ISO UTC) pour le scan des reponses, ou None."""
        return self.mw.db.get_meta("last_reply_check") or self._since_from_earliest()

    def refresh_replies(self):
        """Lit la boite Outlook, associe les reponses et met a jour la base."""
        s = self.mw.settings
        if not s.get("reply_tracking_enabled", False):
            QMessageBox.information(
                self, "Suivi des réponses",
                "Le suivi des réponses n'est pas activé.\n"
                "Active-le dans les paramètres, puis reconnecte-toi une fois "
                "(pour accepter la lecture de la boîte).")
            return
        try:
            token = self.mw.graph.get_token_silent()
        except Exception:
            token = None
        if not token:
            QMessageBox.warning(
                self, "Suivi des réponses",
                "Non connecté à Outlook (ou accès Mail.Read non accepté).\n"
                "Reconnecte-toi dans les paramètres.")
            return

        started = datetime.datetime.now(datetime.timezone.utc)
        since = self._reply_since()
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            messages = self.mw.graph.list_inbox_messages(token, since_iso=since)
            records = replies.build_reply_records(messages)
            result = self.mw.db.apply_replies(records)
            self.mw.db.set_meta("last_reply_check",
                                started.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Suivi des réponses",
                                 f"Échec de la récupération :\n{e}")
            return
        QGuiApplication.restoreOverrideCursor()
        self.reload()
        QMessageBox.information(
            self, "Suivi des réponses",
            f"{result['matched']} réponse(s) associée(s) : "
            f"{result['human']} humaine(s), {result['auto']} automatique(s).\n"
            f"{result['processed']} message(s) analysé(s).")

    def refresh_bounces(self):
        """Lit les rapports de non-remise (NDR), supprime et marque invalide."""
        try:
            token = self.mw.graph.get_token_silent()
        except Exception:
            token = None
        if not token:
            QMessageBox.warning(
                self, "Bounces",
                "Non connecté à Outlook (ou accès Mail.Read non accepté).\n"
                "Reconnecte-toi dans les paramètres.")
            return

        started = datetime.datetime.now(datetime.timezone.utc)
        since = self.mw.db.get_meta("last_bounce_check") or self._since_from_earliest()
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            messages = self.mw.graph.list_inbox_messages(token, since_iso=since)
            sent = self.mw.db.sent_emails_set()
            records = bounces.build_bounce_records(messages, sent)
            result = self.mw.db.apply_bounces(records)
            self.mw.db.set_meta("last_bounce_check",
                                started.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Bounces", f"Échec de la récupération :\n{e}")
            return
        QGuiApplication.restoreOverrideCursor()
        self.reload()
        QMessageBox.information(
            self, "Bounces",
            f"{result['processed']} rapport(s) de non-remise analysé(s).\n"
            f"{result['suppressed']} adresse(s) ajoutée(s) à la liste de suppression, "
            f"{result['marked']} envoi(s) marqué(s) invalide.")

    def export_csv(self):
        if not self._rows:
            QMessageBox.information(self, "Export", "Rien a exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'historique", "historique_envois.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(COLS)
                for r in self._rows:
                    oc = int(r.get("open_count", 0) or 0)
                    opened = "" if oc == 0 else (f"Oui ({oc})" if oc > 1 else "Oui")
                    reply_disp = _reply_display(r.get("reply_type", ""),
                                                r.get("reply_count", 0))
                    if reply_disp == "—":
                        reply_disp = ""
                    w.writerow([r.get("sent_at", ""), r.get("email", ""),
                                r.get("nom", ""), r.get("societe", ""),
                                r.get("status", ""), opened, reply_disp,
                                r.get("campaign", ""), r.get("subject", ""),
                                r.get("error", "")])
            QMessageBox.information(self, "Export", f"Historique exporte :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Echec : {e}")
