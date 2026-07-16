"""
Onglet Destinataires : import d'un fichier Excel/CSV, association des colonnes
aux champs (EMAIL obligatoire, GENRE/PRENOM/NOM/SOCIETE optionnels), apercu et
statistiques (valides / invalides / doublons).
"""

import re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ..core import recipients as rec
from ..core import email_validation as ev

_EMAIL_SYNTAX_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class _ValidationWorker(QThread):
    """Valide les adresses en arriere-plan (MX / SMTP)."""
    progress = Signal(int, int)          # done, total
    done = Signal(dict)                  # {email: (statut, raison)}

    def __init__(self, emails, do_smtp, parent=None):
        super().__init__(parent)
        self.emails = emails
        self.do_smtp = do_smtp
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        results = ev.validate_many(
            self.emails, do_smtp=self.do_smtp, max_workers=8,
            progress_cb=lambda d, t, s, e: self.progress.emit(d, t),
            stop_cb=lambda: self._stop)
        self.done.emit(results)


FIELD_LABELS = [
    ("email", "Colonne EMAIL (obligatoire)"),
    ("genre", "Colonne GENRE (Monsieur/Madame)"),
    ("prenom", "Colonne PRENOM"),
    ("nom", "Colonne NOM"),
    ("societe", "Colonne SOCIETE"),
]


class RecipientsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.df = None
        self.combos = {}
        self._manual = []          # destinataires ajoutes a la main
        self._recipients = []
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
        b_import = QPushButton("Importer un fichier (Excel ou CSV)")
        b_import.setMinimumHeight(38)
        b_import.clicked.connect(self.import_file)
        top.addWidget(b_import)
        b_manual = QPushButton("Ajouter un destinataire")
        b_manual.setMinimumHeight(38)
        b_manual.setToolTip("Ajouter une adresse à la main (sans fichier).")
        b_manual.clicked.connect(self.add_manual_recipient)
        top.addWidget(b_manual)
        self.file_label = QLabel("Aucun fichier importe.")
        self.file_label.setStyleSheet("color:#666;")
        top.addWidget(self.file_label, 1)
        root.addLayout(top)

        # Mapping des colonnes
        self.map_box = QGroupBox("Association des colonnes")
        map_layout = QVBoxLayout(self.map_box)
        for field, label in FIELD_LABELS:
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setMinimumWidth(260)
            combo = QComboBox()
            combo.currentIndexChanged.connect(self.refresh_preview)
            self.combos[field] = combo
            row.addWidget(lab)
            row.addWidget(combo, 1)
            map_layout.addLayout(row)
        self.map_box.setEnabled(False)
        root.addWidget(self.map_box)

        # Verification des adresses (MX / SMTP)
        verify_row = QHBoxLayout()
        self.b_verify = QPushButton("Vérifier les adresses (MX / SMTP)")
        self.b_verify.setMinimumHeight(34)
        self.b_verify.clicked.connect(self.verify_addresses)
        verify_row.addWidget(self.b_verify)
        self.verify_progress = QProgressBar()
        self.verify_progress.setVisible(False)
        verify_row.addWidget(self.verify_progress, 1)
        root.addLayout(verify_row)

        # Statistiques
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-weight:bold; padding:4px;")
        root.addWidget(self.stats_label)

        # Recherche / filtre
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Rechercher :"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("email, nom, prénom, société…")
        self.search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self.search_edit, 1)
        root.addLayout(search_row)

        # Apercu
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Email", "Genre", "Prénom", "Nom", "Société", "Valide", "Vérification"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        self.b_validate = QPushButton("Valider cette liste pour l'envoi")
        self.b_validate.setMinimumHeight(38)
        self.b_validate.clicked.connect(self.validate_list)
        root.addWidget(self.b_validate)
        self._set_validated(False)

    # ------------------------------------------------------------------
    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer une liste", "",
            "Fichiers tableurs (*.xlsx *.xls *.xlsm *.csv);;Tous (*.*)")
        if not path:
            return
        try:
            self.df = rec.read_table(path)
        except Exception as e:
            QMessageBox.critical(self, "Import", f"Lecture impossible :\n{e}")
            return
        self.file_label.setText(f"{path}  ({len(self.df)} lignes)")
        cols = [""] + list(self.df.columns)
        auto = rec.auto_map_columns(self.df.columns)
        for field, combo in self.combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            target = auto.get(field, "")
            if target in self.df.columns:
                combo.setCurrentText(target)
            combo.blockSignals(False)
        self.map_box.setEnabled(True)
        self.refresh_preview()

    def current_mapping(self) -> dict:
        m = {}
        for field, combo in self.combos.items():
            val = combo.currentText().strip()
            if val:
                m[field] = val
        return m

    def refresh_preview(self):
        # Toute modification de la liste/colonnes annule la validation precedente
        self._set_validated(False)
        base = []
        stats = {"total": 0, "valid": 0, "invalid": 0, "duplicates": 0}
        if self.df is not None:
            mapping = self.current_mapping()
            if "email" not in mapping:
                if not self._manual:
                    self.stats_label.setText("Sélectionnez au moins la colonne EMAIL.")
                    self.table.setRowCount(0)
                    return
            else:
                try:
                    base, stats = rec.build_recipients(self.df, mapping)
                except Exception as e:
                    self.stats_label.setText(str(e))
                    return
        combined = self._merge_manual(base)
        if not combined:
            self.stats_label.setText(
                "Importez un fichier (colonne EMAIL) ou ajoutez un destinataire à la main.")
            self.table.setRowCount(0)
            return
        self._apply_suppression(combined)
        stats["total"] = len(combined)
        stats["valid"] = sum(1 for r in combined if r["valid"])
        stats["invalid"] = sum(1 for r in combined if not r["valid"])
        self._recipients = combined
        self._stats = stats
        self._render_table()

    def _merge_manual(self, base):
        """Combine les destinataires du fichier et ceux ajoutes a la main
        (dedoublonnage par adresse, le fichier faisant foi)."""
        seen = {r["email"].strip().lower() for r in base}
        combined = list(base)
        for r in self._manual:
            e = r["email"].strip().lower()
            if e and e not in seen:
                combined.append(dict(r))
                seen.add(e)
        return combined

    def _apply_suppression(self, recipients):
        """Marque INVALIDE les adresses presentes dans la liste de suppression."""
        try:
            supp = self.mw.db.suppression_set()
        except Exception:
            supp = set()
        if not supp:
            return
        for r in recipients:
            if r["email"].strip().lower() in supp:
                r["valid"] = False
                r["validation"] = "SUPPRIMÉ — liste de suppression (bounce/désinscrit)"

    def add_manual_recipient(self):
        """Ouvre un dialogue pour ajouter une adresse a la main."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajouter un destinataire")
        form = QFormLayout(dlg)
        e_email = QLineEdit()
        e_genre = QComboBox()
        e_genre.addItems(["", "Monsieur", "Madame"])
        e_prenom = QLineEdit()
        e_nom = QLineEdit()
        e_societe = QLineEdit()
        form.addRow("Email (obligatoire) :", e_email)
        form.addRow("Genre :", e_genre)
        form.addRow("Prénom :", e_prenom)
        form.addRow("Nom :", e_nom)
        form.addRow("Société :", e_societe)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() != QDialog.Accepted:
            return

        email = e_email.text().strip()
        if not _EMAIL_SYNTAX_RE.match(email):
            QMessageBox.warning(self, "Destinataire",
                                "Adresse email invalide ou vide.")
            return
        if any(r["email"].strip().lower() == email.lower() for r in self._manual):
            QMessageBox.information(self, "Destinataire",
                                    "Cette adresse est déjà dans les ajouts manuels.")
            return
        self._manual.append({
            "email": email,
            "genre": e_genre.currentText().strip(),
            "prenom": e_prenom.text().strip(),
            "nom": e_nom.text().strip(),
            "societe": e_societe.text().strip(),
            "valid": True,
            "validation": "",
        })
        if self.df is None:
            self.file_label.setText(f"{len(self._manual)} destinataire(s) ajouté(s) à la main.")
        self.refresh_preview()

    def _on_search(self):
        if getattr(self, "_recipients", None) is not None:
            self._render_table()

    def _render_table(self):
        stats = self._stats
        q = self.search_edit.text().strip().lower()
        if q:
            rows = [r for r in self._recipients
                    if q in r["email"].lower() or q in r["nom"].lower()
                    or q in r["prenom"].lower() or q in r["societe"].lower()]
        else:
            rows = self._recipients
        self.stats_label.setText(
            f"Total : {stats['total']}    Valides : {stats['valid']}    "
            f"Invalides : {stats['invalid']}    Doublons retirés : {stats['duplicates']}"
            + (f"    (filtre : {len(rows)} trouvé(s))" if q else ""))
        preview = rows[:200]
        self.table.setRowCount(len(preview))
        for i, r in enumerate(preview):
            vals = [r["email"], r["genre"], r["prenom"], r["nom"], r["societe"],
                    "oui" if r["valid"] else "NON", r.get("validation", "")]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if j == 5 and not r["valid"]:
                    item.setForeground(Qt.red)
                if j == 6:
                    txt = str(v).upper()
                    if txt.startswith("VALIDE"):
                        item.setForeground(Qt.darkGreen)
                    elif txt.startswith("INVALIDE"):
                        item.setForeground(Qt.red)
                    elif txt.startswith("INCERTAIN"):
                        item.setForeground(Qt.darkYellow)
                self.table.setItem(i, j, item)

    # ------------------------------------------------------------------
    # Verification des adresses (MX / SMTP)
    # ------------------------------------------------------------------
    def verify_addresses(self):
        worker = getattr(self, "_vworker", None)
        if worker and worker.isRunning():
            worker.request_stop()
            self.b_verify.setText("Arrêt en cours…")
            return
        if self.df is None or not getattr(self, "_recipients", None):
            QMessageBox.warning(self, "Vérification", "Importez d'abord une liste.")
            return
        if not ev.HAS_DNS:
            QMessageBox.warning(
                self, "Vérification",
                "Le module 'dnspython' est manquant : la vérification MX/SMTP est "
                "indisponible. Relancez via le lanceur pour installer les dépendances.")
            return
        r = QMessageBox.question(
            self, "Niveau de vérification",
            "Tester aussi l'existence de chaque adresse via SMTP ?\n\n"
            "Oui = plus précis mais plus lent (port 25, parfois bloqué par le réseau).\n"
            "Non = vérifier seulement le domaine (MX), rapide.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        do_smtp = (r == QMessageBox.Yes)

        emails = [rr["email"] for rr in self._recipients]
        self._vworker = _ValidationWorker(emails, do_smtp)
        self._vworker.progress.connect(self._on_verify_progress)
        self._vworker.done.connect(self._on_verify_done)
        self.verify_progress.setVisible(True)
        self.verify_progress.setValue(0)
        self.b_verify.setText("Arrêter la vérification")
        self._vworker.start()

    def _on_verify_progress(self, done, total):
        self.verify_progress.setMaximum(max(1, total))
        self.verify_progress.setValue(done)
        self.b_verify.setText(f"Arrêter la vérification ({done}/{total})")

    def _on_verify_done(self, results):
        valides = invalides = incertains = 0
        for r in self._recipients:
            res = results.get(r["email"])
            if not res:
                continue
            statut, raison = res
            r["validation"] = f"{statut} — {raison}" if raison else statut
            if statut == "INVALIDE":
                r["valid"] = False
                invalides += 1
            elif statut == "VALIDE":
                valides += 1
            else:
                incertains += 1
        self._stats["valid"] = sum(1 for r in self._recipients if r["valid"])
        self._stats["invalid"] = sum(1 for r in self._recipients if not r["valid"])
        self.verify_progress.setVisible(False)
        self.b_verify.setText("Vérifier les adresses (MX / SMTP)")
        self._set_validated(False)
        self._render_table()
        QMessageBox.information(
            self, "Vérification terminée",
            f"Adresses vérifiées : {len(results)}\n\n"
            f"VALIDE : {valides}    INVALIDE : {invalides}    INCERTAIN : {incertains}\n\n"
            "Les adresses INVALIDE ne seront pas envoyées. "
            "Cliquez ensuite sur « Valider cette liste pour l'envoi ».")

    def _set_validated(self, ok: bool):
        """Met a jour la couleur/texte du bouton selon l'etat de validation."""
        if ok:
            self.b_validate.setText("✓ Liste validée — prête pour l'envoi")
            bg = "#28a745"   # vert
        else:
            self.b_validate.setText("Valider cette liste pour l'envoi")
            bg = "#0d6efd"   # bleu
        self.b_validate.setStyleSheet(
            "QPushButton {"
            f" background-color:{bg}; color:#ffffff; font-weight:bold;"
            " border:none; border-radius:4px; padding:6px 12px; }"
            "QPushButton:disabled { background-color:#d3d3d3; color:#8a8a8a; }"
        )

    def validate_list(self):
        if self.df is None or not getattr(self, "_recipients", None):
            QMessageBox.warning(self, "Liste", "Importez d'abord un fichier valide.")
            return
        valid = [r for r in self._recipients if r["valid"]]
        if not valid:
            QMessageBox.warning(self, "Liste", "Aucune adresse valide dans cette liste.")
            return
        self.mw.recipients = self._recipients
        self.mw.recipients_source = self.file_label.text()
        self._set_validated(True)
        QMessageBox.information(
            self, "Liste validée",
            f"{len(valid)} destinataires valides prêts.\n"
            "Allez dans l'onglet 'File d'attente' pour créer la campagne.")
