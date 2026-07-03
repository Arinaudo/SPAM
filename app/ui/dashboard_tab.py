"""
Onglet Tableau de bord : pour une campagne sélectionnée, récapitulatif
(envoyés / erreurs / invalides / en attente), petit graphique en barres et
export CSV (récap + détail par destinataire).
"""

import csv

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


class _BarChart(QWidget):
    """Petit graphique en barres verticales, sans dépendance externe."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # liste de (label, valeur, QColor)
        self.setMinimumHeight(200)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        margin = 28
        bottom = h - 22
        top = 10
        if not self._data:
            p.setPen(QColor("#888888"))
            p.drawText(self.rect(), Qt.AlignCenter, "Aucune donnée")
            return
        maxval = max((v for _, v, _ in self._data), default=0) or 1
        n = len(self._data)
        slot = (w - 2 * margin) / n
        bar_w = min(80, slot * 0.6)
        for i, (label, val, color) in enumerate(self._data):
            cx = margin + slot * i + slot / 2
            bh = (bottom - top) * (val / maxval)
            x = cx - bar_w / 2
            y = bottom - bh
            p.fillRect(int(x), int(y), int(bar_w), int(bh), color)
            p.setPen(QColor("#222222"))
            p.drawText(int(x - 10), int(y - 6), int(bar_w + 20), 16,
                       Qt.AlignCenter, str(val))
            p.setPen(QColor("#555555"))
            p.drawText(int(cx - slot / 2), bottom + 2, int(slot), 18,
                       Qt.AlignCenter, label)


class DashboardTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._campaign_id = None
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
        top.addWidget(QLabel("Campagne :"))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_campaign_changed)
        top.addWidget(self.combo, 1)
        b_refresh = QPushButton("Actualiser")
        b_refresh.clicked.connect(self.reload)
        top.addWidget(b_refresh)
        b_export = QPushButton("Exporter CSV")
        b_export.clicked.connect(self.export_csv)
        top.addWidget(b_export)
        root.addLayout(top)

        # Récapitulatif chiffré
        recap_box = QGroupBox("Récapitulatif")
        recap_layout = QVBoxLayout(recap_box)
        self.recap_label = QLabel("—")
        self.recap_label.setStyleSheet("font-size:12pt;")
        self.recap_label.setWordWrap(True)
        recap_layout.addWidget(self.recap_label)
        self.rate_label = QLabel("")
        self.rate_label.setStyleSheet("color:#555;")
        recap_layout.addWidget(self.rate_label)
        root.addWidget(recap_box)

        # Graphique
        chart_box = QGroupBox("Répartition")
        chart_layout = QVBoxLayout(chart_box)
        self.chart = _BarChart()
        chart_layout.addWidget(self.chart)
        root.addWidget(chart_box, 1)

    # ------------------------------------------------------------------
    def on_show(self):
        self.reload()

    def reload(self):
        current = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        self._campaigns = self.mw.db.list_campaigns()
        for c in self._campaigns:
            self.combo.addItem(f"#{c['id']} — {c['name']}", c["id"])
        # restaure la sélection
        idx = 0
        if current is not None:
            for i in range(self.combo.count()):
                if self.combo.itemData(i) == current:
                    idx = i
                    break
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._on_campaign_changed()

    def _on_campaign_changed(self):
        self._campaign_id = self.combo.currentData()
        self._render()

    def _render(self):
        if self._campaign_id is None:
            self.recap_label.setText("Aucune campagne.")
            self.rate_label.setText("")
            self.chart.set_data([])
            return
        c = self.mw.db.counts(self._campaign_id)
        sent = c.get("sent", 0)
        error = c.get("error", 0)
        invalid = c.get("invalid", 0)
        pending = c.get("pending", 0)
        total = c.get("total", 0)
        self.recap_label.setText(
            f"Total : {total}    •    Envoyés : {sent}    •    Erreurs : {error}"
            f"    •    Invalides : {invalid}    •    En attente : {pending}")
        sendable = max(1, total - invalid)
        taux = 100.0 * sent / sendable
        self.rate_label.setText(
            f"Taux d'envoi : {taux:.1f} %  (sur {sendable} adresses valides). "
            "Les « invalides » sont les adresses écartées avant envoi.")
        self.chart.set_data([
            ("Envoyés", sent, QColor("#28a745")),
            ("Erreurs", error, QColor("#dc3545")),
            ("Invalides", invalid, QColor("#fd7e14")),
            ("En attente", pending, QColor("#6c757d")),
        ])

    def export_csv(self):
        if self._campaign_id is None:
            QMessageBox.information(self, "Export", "Aucune campagne sélectionnée.")
            return
        c = self.mw.db.get_campaign(self._campaign_id)
        counts = self.mw.db.counts(self._campaign_id)
        items = self.mw.db.items(self._campaign_id)
        default = f"campagne_{self._campaign_id}_rapport.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le rapport", default, "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Campagne", c.get("name", "")])
                w.writerow(["Objet", c.get("subject", "")])
                w.writerow(["Créée le", c.get("created_at", "")])
                w.writerow([])
                w.writerow(["Total", counts.get("total", 0)])
                w.writerow(["Envoyés", counts.get("sent", 0)])
                w.writerow(["Erreurs", counts.get("error", 0)])
                w.writerow(["Invalides", counts.get("invalid", 0)])
                w.writerow(["En attente", counts.get("pending", 0)])
                w.writerow([])
                w.writerow(["Email", "Prénom", "Nom", "Société",
                            "Statut", "Erreur", "Envoyé le"])
                for it in items:
                    w.writerow([it.get("email", ""), it.get("prenom", ""),
                                it.get("nom", ""), it.get("societe", ""),
                                it.get("status", ""), it.get("error", ""),
                                it.get("sent_at", "")])
            QMessageBox.information(self, "Export", f"Rapport exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export", f"Échec : {e}")
