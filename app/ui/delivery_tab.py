"""
Onglet Délivrabilité :
- Test d'authentification du domaine (SPF / DKIM / DMARC) en direct.
- Analyse anti-spam du mail en cours.
- Réglage de la cadence d'envoi (enregistré automatiquement).
- Recommandations.
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSpinBox, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ..core import domain_auth, content_check

RECOMMANDATIONS_HTML = """
<h3 style="color:#0563C1;">Comment éviter de finir dans les spams</h3>
<p><b>1. Authentifier le domaine (le plus important).</b> Activez
<b>DKIM</b> et <b>DMARC</b> sur <i>castignac.com</i> (SPF est déjà en place).
Cause n°1 de passage en spam ; testez l'état ci-dessus.</p>
<p><b>2. Nettoyer la liste.</b> « Vérifier les adresses » dans l'onglet
Destinataires ; n'envoyez pas aux adresses déjà en erreur.</p>
<p><b>3. Monter en charge progressivement.</b> Quelques centaines/jour au
début, puis augmentez sur 2–3 semaines.</p>
<p><b>4. Espacer les envois.</b> Délai de quelques secondes entre mails +
pauses entre lots (réglable ci-dessous).</p>
<p><b>5. Soigner le contenu.</b> Évitez swisstransfer/wetransfer, les liens
http://, les images lourdes, les MAJUSCULES et le vocabulaire trop
commercial. Utilisez l'analyse ci-dessus.</p>
<p><b>6. Personnaliser.</b> Civilité + variation des politesses : laissez
activé.</p>
<p><b>7. Toujours envoyer un test</b> avant une vraie campagne (Composer).</p>
<p><b>8. Surveiller sa réputation</b> via Google Postmaster Tools et
Microsoft SNDS.</p>
"""


class _AuthWorker(QThread):
    done = Signal(list)

    def __init__(self, domain, parent=None):
        super().__init__(parent)
        self.domain = domain

    def run(self):
        self.done.emit(domain_auth.check_all(self.domain))


_ICONS = {"ok": ("✅", "#1e7e34"), "warn": ("⚠️", "#b8860b"),
          "missing": ("❌", "#c0392b"), "bad": ("❌", "#c0392b"),
          "error": ("⛔", "#777777")}


class DeliveryTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._loading = False
        self._authworker = None
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        root = QVBoxLayout(inner)

        # --- 1. Authentification du domaine ---
        auth_box = QGroupBox("Test d'authentification du domaine (SPF / DKIM / DMARC)")
        auth_layout = QVBoxLayout(auth_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Domaine :"))
        self.domain_edit = QLineEdit("castignac.com")
        row.addWidget(self.domain_edit, 1)
        self.b_auth = QPushButton("Vérifier")
        self.b_auth.clicked.connect(self.verify_auth)
        row.addWidget(self.b_auth)
        auth_layout.addLayout(row)
        self.auth_result = QLabel("Cliquez sur « Vérifier » pour tester le domaine.")
        self.auth_result.setTextFormat(Qt.RichText)
        self.auth_result.setWordWrap(True)
        self.auth_result.setOpenExternalLinks(True)
        auth_layout.addWidget(self.auth_result)
        root.addWidget(auth_box)

        # --- 2. Analyse anti-spam du mail ---
        content_box = QGroupBox("Analyse anti-spam du mail en cours")
        content_layout = QVBoxLayout(content_box)
        self.b_analyze = QPushButton("Analyser le mail du Composer")
        self.b_analyze.clicked.connect(self.analyze_content)
        content_layout.addWidget(self.b_analyze)
        self.content_result = QTextBrowser()
        self.content_result.setMinimumHeight(180)
        self.content_result.setHtml(
            "<p style='color:#888;'>Composez votre mail, puis cliquez sur "
            "« Analyser le mail du Composer ».</p>")
        content_layout.addWidget(self.content_result)
        root.addWidget(content_box)

        # --- 3. Cadence ---
        cad_box = QGroupBox("Cadence d'envoi (modifiable ici, anti-spam)")
        form = QFormLayout(cad_box)
        self.delay_min = QDoubleSpinBox(); self.delay_min.setRange(0.5, 600); self.delay_min.setSuffix(" s")
        self.delay_max = QDoubleSpinBox(); self.delay_max.setRange(0.5, 600); self.delay_max.setSuffix(" s")
        self.batch_size = QSpinBox(); self.batch_size.setRange(1, 100000)
        self.batch_pause_min = QDoubleSpinBox(); self.batch_pause_min.setRange(0, 36000); self.batch_pause_min.setSuffix(" s")
        self.batch_pause_max = QDoubleSpinBox(); self.batch_pause_max.setRange(0, 36000); self.batch_pause_max.setSuffix(" s")
        form.addRow("Délai minimum entre deux mails :", self.delay_min)
        form.addRow("Délai maximum entre deux mails :", self.delay_max)
        form.addRow("Taille d'un lot (mails) :", self.batch_size)
        form.addRow("Pause minimum entre lots :", self.batch_pause_min)
        form.addRow("Pause maximum entre lots :", self.batch_pause_max)
        self.save_to_sent = QCheckBox("Enregistrer une copie dans les Éléments envoyés")
        self.add_ref = QCheckBox("Ajouter une référence invisible unique par mail (anti-spam)")
        form.addRow(self.save_to_sent)
        form.addRow(self.add_ref)
        info = QLabel("Conseil : 5–8 s entre deux mails. Enregistré automatiquement.")
        info.setStyleSheet("color:#595959;")
        info.setWordWrap(True)
        form.addRow(info)
        root.addWidget(cad_box)

        for w in (self.delay_min, self.delay_max, self.batch_pause_min, self.batch_pause_max):
            w.valueChanged.connect(self._save)
        self.batch_size.valueChanged.connect(self._save)
        self.save_to_sent.toggled.connect(self._save)
        self.add_ref.toggled.connect(self._save)

        # --- 4. Recommandations ---
        rec_box = QGroupBox("Recommandations")
        rec_layout = QVBoxLayout(rec_box)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(RECOMMANDATIONS_HTML)
        browser.setMinimumHeight(240)
        rec_layout.addWidget(browser)
        root.addWidget(rec_box)

        root.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Authentification domaine
    # ------------------------------------------------------------------
    def verify_auth(self):
        if self._authworker and self._authworker.isRunning():
            return
        if not domain_auth.HAS_DNS:
            self.auth_result.setText(
                "<span style='color:#c0392b;'>Module dnspython manquant : "
                "relancez via le lanceur pour l'installer.</span>")
            return
        domain = self.domain_edit.text().strip()
        self.b_auth.setEnabled(False)
        self.auth_result.setText("Vérification DNS en cours…")
        self._authworker = _AuthWorker(domain)
        self._authworker.done.connect(self._on_auth_done)
        self._authworker.start()

    def _on_auth_done(self, results):
        self.b_auth.setEnabled(True)
        lines = []
        for name, status, detail in results:
            icon, color = _ICONS.get(status, ("•", "#000000"))
            lines.append(
                f"<p style='margin:4px 0;'>{icon} <b style='color:{color};'>{name}</b> — "
                f"<span style='color:#333;'>{detail}</span></p>")
        # conseil si DKIM/DMARC manquants
        statuses = {n: s for n, s, _ in results}
        if statuses.get("DKIM") == "missing" or statuses.get("DMARC") in ("missing", "warn"):
            lines.append(
                "<p style='color:#595959;margin-top:8px;'><i>DKIM/DMARC s'activent "
                "côté DNS (OVH) + administration Microsoft 365. C'est le levier n°1 "
                "contre le spam.</i></p>")
        self.auth_result.setText("".join(lines) or "Aucun résultat.")

    # ------------------------------------------------------------------
    # Analyse du contenu
    # ------------------------------------------------------------------
    def analyze_content(self):
        compose = self.mw.compose_tab
        html = compose.get_full_html()
        subject = compose.get_subject()
        images = compose.get_images()
        score, issues = content_check.analyze(html, subject, images)
        if score >= 80:
            scolor = "#1e7e34"
        elif score >= 50:
            scolor = "#b8860b"
        else:
            scolor = "#c0392b"
        parts = [f"<h3 style='margin:0 0 8px;'>Score : "
                 f"<span style='color:{scolor};'>{score}/100</span></h3>"]
        for lvl, label, detail in issues:
            icon, color = _ICONS.get(lvl, ("•", "#000"))
            d = f" — <span style='color:#555;'>{detail}</span>" if detail else ""
            parts.append(f"<p style='margin:3px 0;'>{icon} "
                         f"<b style='color:{color};'>{label}</b>{d}</p>")
        self.content_result.setHtml("".join(parts))

    # ------------------------------------------------------------------
    # Cadence (réglages)
    # ------------------------------------------------------------------
    def _load(self):
        self._loading = True
        s = self.mw.settings
        self.delay_min.setValue(float(s.get("delay_min", 5.0)))
        self.delay_max.setValue(float(s.get("delay_max", 8.0)))
        self.batch_size.setValue(int(s.get("batch_size", 100)))
        self.batch_pause_min.setValue(float(s.get("batch_pause_min", 60.0)))
        self.batch_pause_max.setValue(float(s.get("batch_pause_max", 120.0)))
        self.save_to_sent.setChecked(bool(s.get("save_to_sent", True)))
        self.add_ref.setChecked(bool(s.get("add_invisible_ref", True)))
        self._loading = False

    def on_show(self):
        self._load()

    def _save(self):
        if self._loading:
            return
        s = self.mw.settings
        dmin = self.delay_min.value()
        dmax = max(self.delay_max.value(), dmin)
        pmin = self.batch_pause_min.value()
        pmax = max(self.batch_pause_max.value(), pmin)
        s.update({
            "delay_min": dmin,
            "delay_max": dmax,
            "batch_size": self.batch_size.value(),
            "batch_pause_min": pmin,
            "batch_pause_max": pmax,
            "save_to_sent": self.save_to_sent.isChecked(),
            "add_invisible_ref": self.add_ref.isChecked(),
        })
        s.save()
