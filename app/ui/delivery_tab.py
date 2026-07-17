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
from . import theme
from .widgets import NoScrollDoubleSpinBox, NoScrollSpinBox

RECOMMANDATIONS_HTML = """
<h3 style="color:__ACCENT__;">Comment éviter de finir dans les spams</h3>
<p style="color:__MUTED__;">Aucune astuce ne garantit 100&nbsp;% la boîte de réception.
La délivrabilité est la somme de plusieurs bonnes pratiques : authentification,
réputation, qualité de la liste, contenu et régularité. Voici la liste
complète, de la plus importante à la plus fine.</p>

<h4 style="color:__ACCENT__;">1. Authentifier le domaine (priorité absolue)</h4>
<p>C'est la cause n°1 de passage en spam. Sur <i>castignac.com</i> :</p>
<ul>
<li><b>SPF</b> : autorise les serveurs qui envoient pour ton domaine (déjà en place).</li>
<li><b>DKIM</b> : signe cryptographiquement chaque mail. À activer côté Microsoft 365.</li>
<li><b>DMARC</b> : indique quoi faire si SPF/DKIM échouent. Commence en
<i>p=none</i> pour observer, puis passe à <i>quarantine</i>.</li>
<li><b>Alignement</b> : l'adresse d'expéditeur visible doit être sur le domaine
authentifié (envoie depuis <i>@castignac.com</i>, pas depuis une adresse générique).</li>
</ul>
<p>Teste l'état réel avec le bouton ci-dessus et avec mail-tester.com.</p>

<h4 style="color:__ACCENT__;">2. Réputation et montée en charge progressive</h4>
<p>Un domaine qui se met soudain à envoyer des milliers de mails est traité
comme suspect. Monte en charge sur 2 à 4 semaines : commence par quelques
dizaines puis centaines par jour, augmente régulièrement si les taux de
plainte et de rebond restent bas. Envoie à un rythme régulier plutôt que par
gros pics ponctuels.</p>

<h4 style="color:__ACCENT__;">3. Hygiène de la liste</h4>
<p>Une liste sale détruit la réputation plus vite que tout le reste.</p>
<ul>
<li>Valide les adresses (onglet Destinataires, « Vérifier les adresses »).</li>
<li>Ne renvoie jamais aux adresses déjà en erreur ; l'app les marque, retire-les.</li>
<li>Un taux de rebond élevé (&gt; 3&nbsp;%) fait chuter la réputation : nettoie avant d'envoyer.</li>
<li>N'utilise pas de listes achetées ou scrappées au hasard : risque de
<i>spam traps</i> (adresses pièges) qui te blacklistent.</li>
</ul>

<h4 style="color:__ACCENT__;">4. Cadence d'envoi</h4>
<p>Espace les envois : un délai de quelques secondes entre deux mails et des
pauses entre lots (réglable ci-dessous) imitent un envoi humain. Évite d'envoyer
tout un fichier d'un bloc. Privilégie les heures ouvrées.</p>

<h4 style="color:__ACCENT__;">5. Contenu du mail</h4>
<ul>
<li>Garde un bon ratio texte / image : un mail tout en image (une grande
bannière et rien d'autre) est un signal spam fort.</li>
<li>Évite les images trop lourdes ; héberge-les ou attache-les en inline léger.</li>
<li>Bannis les liens en <i>http://</i> (uniquement <i>https://</i>) et les
raccourcisseurs (bit.ly...).</li>
<li>Évite swisstransfer / wetransfer et les domaines de partage de fichiers.</li>
<li>Pas de MAJUSCULES criardes, d'excès de « !!! », d'emojis à répétition ni de
vocabulaire trop commercial (« gratuit », « offre exceptionnelle », « urgent »).</li>
<li>Soigne l'orthographe : les fautes dégradent le score anti-spam.</li>
<li>Un objet honnête et clair, sans clickbait ni faux « RE:&nbsp;» / « FW:&nbsp;».</li>
<li>Utilise l'analyse anti-spam du mail ci-dessus avant d'envoyer.</li>
</ul>

<h4 style="color:__ACCENT__;">6. Pièces jointes et liens</h4>
<p>En prospection à froid, une pièce jointe augmente le risque de spam. Préfère
un <b>lien de téléchargement</b> dans le corps du mail plutôt qu'un fichier
attaché. Si tu joins quand même un document : un <b>PDF léger</b> (&lt; 3&nbsp;Mo),
jamais de .zip, ni de fichiers Office à macros (.docm / .xlsm), ni d'exécutables.</p>

<h4 style="color:__ACCENT__;">7. Personnalisation et variation</h4>
<p>Des milliers de mails strictement identiques forment une empreinte facile à
filtrer. Laisse activés la civilité (Monsieur / Madame), la variation des
formules de politesse et la référence unique par mail. Personnalise avec les
champs de fusion ({PRENOM}, {SOCIETE}...).</p>

<h4 style="color:__ACCENT__;">8. Désinscription et conformité (RGPD)</h4>
<p>Un lien de désinscription clair est à la fois une obligation légale et un
signal positif pour les filtres. Honore immédiatement les désabonnements et ne
recontacte jamais un désinscrit. Ajoute tes mentions d'expéditeur (identité,
coordonnées). Un destinataire qui peut se désinscrire ne te classe pas en spam,
ce qui protège ta réputation.</p>

<h4 style="color:__ACCENT__;">9. Engagement des destinataires</h4>
<p>Les messageries observent qui ouvre et répond. Concentre tes envois sur les
contacts qui interagissent, et retire progressivement ceux qui n'ouvrent jamais.
Un mail d'un expéditeur souvent ignoré finit en spam pour tout le monde. Le suivi
d'ouverture (onglet Paramètres) aide à repérer les contacts inactifs.</p>

<h4 style="color:__ACCENT__;">10. Expéditeur et en-têtes</h4>
<p>Utilise un nom d'expéditeur cohérent et stable (par ex. « Prénom Nom –
Castignac »). L'adresse doit être réelle et capable de recevoir des réponses :
une adresse qui n'accepte pas de retour (no-reply mal configuré) est mal vue.
Évite de changer d'adresse d'expédition à chaque campagne.</p>

<h4 style="color:__ACCENT__;">11. Surveiller sa réputation</h4>
<p>Mesure au lieu de deviner :</p>
<ul>
<li><b>Google Postmaster Tools</b> : réputation domaine/IP et taux de plainte côté Gmail.</li>
<li><b>Microsoft SNDS / JMRP</b> : réputation côté Outlook / Hotmail.</li>
<li><b>mail-tester.com</b> : score détaillé avant campagne.</li>
<li>Garde le <b>taux de plainte sous 0,3&nbsp;%</b> ; au-delà, la délivrabilité s'effondre.</li>
<li>Vérifie que ton domaine/IP n'est pas sur une blacklist (mxtoolbox.com).</li>
</ul>

<h4 style="color:__ACCENT__;">12. Toujours tester avant d'envoyer</h4>
<p>Avant chaque vraie campagne, envoie-toi un test (onglet Composer) et vérifie
le rendu, les liens, la présence en boîte de réception sur plusieurs
fournisseurs (Gmail, Outlook, Yahoo).</p>
"""


class _AuthWorker(QThread):
    done = Signal(list)

    def __init__(self, domain, parent=None):
        super().__init__(parent)
        self.domain = domain

    def run(self):
        self.done.emit(domain_auth.check_all(self.domain))


# Couleurs d'etat choisies pour rester lisibles en theme sombre comme clair.
_ICONS = {"ok": ("✅", "#2FA968"), "warn": ("⚠️", "#D0A02A"),
          "missing": ("❌", "#E06666"), "bad": ("❌", "#E06666"),
          "error": ("⛔", "#9AA0A6")}


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
            f"<p style='color:{theme.hint()};'>Composez votre mail, puis cliquez sur "
            "« Analyser le mail du Composer ».</p>")
        content_layout.addWidget(self.content_result)
        root.addWidget(content_box)

        # --- 3. Cadence ---
        cad_box = QGroupBox("Cadence d'envoi (modifiable ici, anti-spam)")
        form = QFormLayout(cad_box)
        self.delay_min = NoScrollDoubleSpinBox(); self.delay_min.setRange(0.5, 600); self.delay_min.setSuffix(" s")
        self.delay_max = NoScrollDoubleSpinBox(); self.delay_max.setRange(0.5, 600); self.delay_max.setSuffix(" s")
        self.batch_size = NoScrollSpinBox(); self.batch_size.setRange(1, 100000)
        self.batch_pause_min = NoScrollDoubleSpinBox(); self.batch_pause_min.setRange(0, 36000); self.batch_pause_min.setSuffix(" s")
        self.batch_pause_max = NoScrollDoubleSpinBox(); self.batch_pause_max.setRange(0, 36000); self.batch_pause_max.setSuffix(" s")
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
        info.setStyleSheet(f"color:{theme.hint()};")
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
        browser.setHtml(RECOMMANDATIONS_HTML
                        .replace("__ACCENT__", theme.accent())
                        .replace("__MUTED__", theme.muted()))
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
            icon, color = _ICONS.get(status, ("•", theme.muted()))
            lines.append(
                f"<p style='margin:4px 0;'>{icon} <b style='color:{color};'>{name}</b> — "
                f"<span style='color:{theme.muted()};'>{detail}</span></p>")
        # conseil si DKIM/DMARC manquants
        statuses = {n: s for n, s, _ in results}
        if statuses.get("DKIM") == "missing" or statuses.get("DMARC") in ("missing", "warn"):
            lines.append(
                f"<p style='color:{theme.hint()};margin-top:8px;'><i>DKIM/DMARC s'activent "
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
            icon, color = _ICONS.get(lvl, ("•", theme.muted()))
            d = f" — <span style='color:{theme.muted()};'>{detail}</span>" if detail else ""
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
