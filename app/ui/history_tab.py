"""
Onglet Historique : liste de tous les mails traites (envoyes / en erreur),
toutes campagnes confondues, avec recherche, filtre par statut et export CSV.
"""

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

COLS = ["Date", "Email", "Nom", "Société", "Statut", "Campagne", "Objet", "Erreur"]


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
            vals = [r.get("sent_at", ""), r.get("email", ""), r.get("nom", ""),
                    r.get("societe", ""), r.get("status", ""), r.get("campaign", ""),
                    r.get("subject", ""), r.get("error", "")]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 4 and r.get("status") == "error":
                    item.setForeground(Qt.red)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

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
                    w.writerow([r.get("sent_at", ""), r.get("email", ""),
                                r.get("nom", ""), r.get("societe", ""),
                                r.get("status", ""), r.get("campaign", ""),
                                r.get("subject", ""), r.get("error", "")])
            QMessageBox.information(self, "Export", f"Historique exporte :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Echec : {e}")
