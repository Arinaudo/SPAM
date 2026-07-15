"""
Onglet File d'attente : creation d'une campagne (Composer + Destinataires),
suivi de la progression d'un envoi long (barre de progression, compteurs, ETA),
et controles Demarrer / Pause / Reprendre / Arreter. La progression est
persistee : on peut fermer l'app et reprendre plus tard.
"""

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.sender import SendWorker
from ..core.keepawake import KeepAwake


class QueueTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.worker = None
        self.current_campaign_id = None
        self.keepawake = KeepAwake()
        self._build_ui()
        self.refresh_campaigns()

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

        # Selection / creation de campagne
        sel_box = QGroupBox("Campagne")
        sel_layout = QHBoxLayout(sel_box)
        self.campaign_combo = QComboBox()
        self.campaign_combo.currentIndexChanged.connect(self._on_campaign_changed)
        sel_layout.addWidget(self.campaign_combo, 1)
        b_new = QPushButton("Créer depuis Composer + Destinataires")
        b_new.clicked.connect(self.create_campaign)
        sel_layout.addWidget(b_new)
        b_refresh = QPushButton("Actualiser")
        b_refresh.clicked.connect(self.refresh_campaigns)
        sel_layout.addWidget(b_refresh)
        b_dup = QPushButton("Dupliquer dans le Composer")
        b_dup.clicked.connect(self.duplicate_campaign)
        sel_layout.addWidget(b_dup)
        b_del = QPushButton("Supprimer")
        b_del.clicked.connect(self.delete_campaign)
        sel_layout.addWidget(b_del)
        root.addWidget(sel_box)

        # Progression
        prog_box = QGroupBox("Progression")
        prog_layout = QVBoxLayout(prog_box)
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(26)
        prog_layout.addWidget(self.progress)
        self.counts_label = QLabel("—")
        self.counts_label.setStyleSheet("font-weight:bold;")
        prog_layout.addWidget(self.counts_label)
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color:#555;")
        prog_layout.addWidget(self.eta_label)
        root.addWidget(prog_box)

        # Controles
        ctrl = QHBoxLayout()
        self.b_start = QPushButton("Démarrer l'envoi")
        self.b_start.clicked.connect(self.start_sending)
        self.b_pause = QPushButton("Pause")
        self.b_pause.clicked.connect(self.pause_resume)
        self.b_stop = QPushButton("Arrêter")
        self.b_stop.clicked.connect(lambda: self.stop_sending(wait=False))
        self.b_retry = QPushButton("Re-tenter les erreurs")
        self.b_retry.clicked.connect(self.retry_errors)
        # Couleurs pour reperer les actions d'un coup d'oeil
        self.b_start.setStyleSheet(self._btn_style("#28a745"))   # vert
        self.b_pause.setStyleSheet(self._btn_style("#f0ad4e", fg="#3b2f00"))  # jaune
        self.b_stop.setStyleSheet(self._btn_style("#dc3545"))    # rouge
        self.b_retry.setStyleSheet(self._btn_style("#6c757d"))   # gris
        for b in (self.b_start, self.b_pause, self.b_stop, self.b_retry):
            b.setMinimumHeight(40)
            ctrl.addWidget(b)
        root.addLayout(ctrl)

        # Journal
        root.addWidget(QLabel("Journal :"))
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        root.addWidget(self.logbox, 1)

        self._set_controls(running=False)

    # ------------------------------------------------------------------
    # Campagnes
    # ------------------------------------------------------------------
    def refresh_campaigns(self):
        self.campaign_combo.blockSignals(True)
        self.campaign_combo.clear()
        self._campaigns = self.mw.db.list_campaigns()
        for c in self._campaigns:
            counts = self.mw.db.counts(c["id"])
            label = (f"#{c['id']} — {c['name']}  [{c['status']}]  "
                     f"{counts['sent']}/{counts['total']} envoyes")
            self.campaign_combo.addItem(label, c["id"])
        self.campaign_combo.blockSignals(False)
        if self._campaigns:
            self.campaign_combo.setCurrentIndex(0)
            self._on_campaign_changed()
        else:
            self.current_campaign_id = None
            self._update_progress_display()

    def _on_campaign_changed(self):
        cid = self.campaign_combo.currentData()
        self.current_campaign_id = cid
        self._update_progress_display()

    def create_campaign(self):
        err = self.mw.compose_tab.validate()
        if err:
            QMessageBox.warning(self, "Composer", err)
            self.mw.tabs.setCurrentWidget(self.mw.compose_tab)
            return
        recipients = [r for r in self.mw.recipients]
        if not recipients:
            QMessageBox.warning(self, "Destinataires",
                                "Aucune liste validee. Allez dans l'onglet Destinataires.")
            self.mw.tabs.setCurrentWidget(self.mw.recipients_tab)
            return

        subject = self.mw.compose_tab.get_subject()
        html = self.mw.compose_tab.get_full_html()
        images = self.mw.compose_tab.get_images()
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        name = f"{subject[:40]} — {ts}"

        cid = self.mw.db.create_campaign(
            name=name, subject=subject, body_html=html, images=images,
            recipients=recipients,
            delay_min=self.mw.settings.get("delay_min", 5.0),
            delay_max=self.mw.settings.get("delay_max", 8.0),
            save_to_sent=self.mw.settings.get("save_to_sent", True),
            add_ref=self.mw.settings.get("add_invisible_ref", True),
            greetings=self.mw.compose_tab.get_greetings(),
            closings=self.mw.compose_tab.get_closings(),
            signature=self.mw.compose_tab.get_signature(),
            attachments=self.mw.compose_tab.get_attachments(),
        )
        counts = self.mw.db.counts(cid)
        self.refresh_campaigns()
        self._select_campaign(cid)
        QMessageBox.information(
            self, "Campagne creee",
            f"Campagne #{cid} creee : {counts['pending']} a envoyer, "
            f"{counts['invalid']} invalides ignores.\n"
            "Cliquez sur 'Demarrer l'envoi'.")

    def _select_campaign(self, cid):
        for i in range(self.campaign_combo.count()):
            if self.campaign_combo.itemData(i) == cid:
                self.campaign_combo.setCurrentIndex(i)
                return

    def duplicate_campaign(self):
        if self.current_campaign_id is None:
            QMessageBox.warning(self, "Campagne", "Sélectionnez une campagne.")
            return
        import json
        c = self.mw.db.get_campaign(self.current_campaign_id)
        if not c:
            return
        try:
            images = json.loads(c.get("images_json") or "{}")
        except Exception:
            images = {}
        try:
            closings = json.loads(c.get("closings_json") or "[]")
        except Exception:
            closings = []
        try:
            attachments = json.loads(c.get("attachments_json") or "[]")
        except Exception:
            attachments = []
        greetings = {
            "greeting_monsieur": c.get("greeting_monsieur", ""),
            "greeting_madame": c.get("greeting_madame", ""),
            "greeting_fallback": c.get("greeting_fallback", ""),
        }
        self.mw.compose_tab.load_content(
            c["subject"], c["body_html"], images, greetings,
            closings, c.get("signature_html", ""), attachments=attachments)
        self.mw.tabs.setCurrentWidget(self.mw.compose_tab)
        QMessageBox.information(
            self, "Campagne dupliquée",
            "Le contenu a été chargé dans le Composer.\n"
            "Importez/validez une nouvelle liste (onglet Destinataires) puis "
            "créez la campagne.")

    def delete_campaign(self):
        if self.current_campaign_id is None:
            return
        if self.is_sending():
            QMessageBox.warning(self, "Envoi en cours", "Arretez l'envoi avant de supprimer.")
            return
        r = QMessageBox.question(self, "Supprimer",
                                 "Supprimer cette campagne et son historique d'envoi ?")
        if r == QMessageBox.Yes:
            self.mw.db.delete_campaign(self.current_campaign_id)
            self.refresh_campaigns()

    # ------------------------------------------------------------------
    # Envoi
    # ------------------------------------------------------------------
    def start_sending(self):
        if self.current_campaign_id is None:
            QMessageBox.warning(self, "Campagne", "Selectionnez ou creez une campagne.")
            return
        if self.is_sending():
            return

        # Connexion Outlook si necessaire (interactive sur le thread principal)
        if not self.mw.graph.is_logged_in():
            r = QMessageBox.question(
                self, "Connexion Outlook",
                "Vous n'etes pas connecte a Outlook. Se connecter maintenant ?")
            if r != QMessageBox.Yes:
                return
            try:
                self.mw.graph.get_token_interactive()
                self.mw.refresh_account_status()
            except Exception as e:
                QMessageBox.critical(self, "Connexion", f"Echec : {e}")
                return

        counts = self.mw.db.counts(self.current_campaign_id)
        if counts["pending"] == 0:
            QMessageBox.information(self, "Rien a envoyer",
                                    "Aucun destinataire en attente dans cette campagne.")
            return

        # Confirmation avant tout envoi réel
        pending = counts["pending"]
        avg = (self.mw.settings.get("delay_min", 5.0) +
               self.mw.settings.get("delay_max", 8.0)) / 2.0
        duree = self._fmt_duration(int(pending * avg))
        info = self.mw.graph.signed_in_user()
        expediteur = info[1] if info and info[1] else "votre compte Outlook"
        confirm = QMessageBox.question(
            self, "Confirmer l'envoi",
            f"Vous allez envoyer {pending} mail(s) depuis :\n{expediteur}\n\n"
            f"Durée estimée : {duree}.\n\n"
            "Démarrer l'envoi maintenant ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        self.worker = SendWorker(self.mw.db, self.mw.graph,
                                 self.current_campaign_id, self.mw.settings)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._append_log)
        self.worker.finished_reason.connect(self._on_finished)
        self.worker.start()
        if self.mw.settings.get("prevent_sleep", True):
            self.keepawake.start()
            if self.keepawake.is_active():
                self._append_log("Mise en veille du PC désactivée pendant l'envoi.")
        self._set_controls(running=True)
        self._append_log(f"=== Demarrage campagne #{self.current_campaign_id} ===")

    def pause_resume(self):
        if not self.worker:
            return
        if self.b_pause.text() == "Pause":
            self.worker.pause()
            self.b_pause.setText("Reprendre")
        else:
            self.worker.resume()
            self.b_pause.setText("Pause")

    def stop_sending(self, wait=False):
        if not self.worker:
            return
        self.worker.request_stop()
        self._append_log("Arret demande...")
        if wait:
            self.worker.wait(5000)

    def retry_errors(self):
        if self.current_campaign_id is None or self.is_sending():
            return
        self.mw.db.reset_errors_to_pending(self.current_campaign_id)
        self._update_progress_display()
        self._append_log("Erreurs remises en file d'attente.")
        self.refresh_campaigns()
        self._select_campaign(self.current_campaign_id)

    # ------------------------------------------------------------------
    # Signaux worker
    # ------------------------------------------------------------------
    def _on_progress(self, c):
        self._render_counts(c)

    def _on_finished(self, reason):
        self.keepawake.stop()
        self._set_controls(running=False)
        self.b_pause.setText("Pause")
        labels = {"completed": "Campagne terminée.",
                  "stopped": "Envoi arrêté (reprenable plus tard).",
                  "auth_error": "Erreur de connexion Outlook."}
        self._append_log("=== " + labels.get(reason, reason) + " ===")
        self.worker = None
        self.refresh_campaigns()
        self._select_campaign(self.current_campaign_id)
        if reason == "completed":
            QMessageBox.information(self, "Termine", "La campagne est terminee.")

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------
    def _update_progress_display(self):
        if self.current_campaign_id is None:
            self.progress.setValue(0)
            self.counts_label.setText("—")
            self.eta_label.setText("")
            return
        c = self.mw.db.counts(self.current_campaign_id)
        self._render_counts(c)

    def _render_counts(self, c):
        total = c.get("total", 0)
        done = c.get("sent", 0) + c.get("error", 0) + c.get("invalid", 0)
        sendable = total - c.get("invalid", 0)
        self.progress.setMaximum(max(1, sendable))
        self.progress.setValue(c.get("sent", 0) + c.get("error", 0))
        self.counts_label.setText(
            f"Envoyés : {c.get('sent',0)}   Erreurs : {c.get('error',0)}   "
            f"En attente : {c.get('pending',0)}   Invalides : {c.get('invalid',0)}   "
            f"Total : {total}")
        pending = c.get("pending", 0)
        avg = (self.mw.settings.get("delay_min", 5.0) +
               self.mw.settings.get("delay_max", 8.0)) / 2.0
        secs = int(pending * avg)
        if pending and self.is_sending():
            self.eta_label.setText(f"Temps restant estimé : {self._fmt_duration(secs)} "
                                   f"(~{avg:.0f}s/mail)")
        else:
            self.eta_label.setText("")

    @staticmethod
    def _fmt_duration(secs):
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h{m:02d}"
        if m:
            return f"{m} min {s:02d}s"
        return f"{s}s"

    def _append_log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.logbox.appendPlainText(f"[{ts}] {msg}")

    @staticmethod
    def _btn_style(bg, fg="#ffffff"):
        return (
            "QPushButton {"
            f" background-color:{bg}; color:{fg}; font-weight:bold;"
            " border:none; border-radius:4px; padding:6px 12px; }"
            "QPushButton:disabled { background-color:#d3d3d3; color:#8a8a8a; }"
        )

    def _set_controls(self, running):
        self.b_start.setEnabled(not running)
        self.b_pause.setEnabled(running)
        self.b_stop.setEnabled(running)
        self.b_retry.setEnabled(not running)
        self.campaign_combo.setEnabled(not running)

    # ------------------------------------------------------------------
    def is_sending(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def on_show(self):
        if not self.is_sending():
            self.refresh_campaigns()
