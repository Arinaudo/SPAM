"""
Onglet Parametres : connexion au compte Outlook, configuration Azure
(Client ID / Tenant), cadence d'envoi, contenu par defaut et options anti-spam.
"""

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)


class SettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build_ui()
        self._load()

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
        s = self.mw.settings

        # --- Compte Outlook ---
        acc_box = QGroupBox("Compte Outlook (Microsoft Graph)")
        acc_layout = QVBoxLayout(acc_box)
        self.account_status = QLabel()
        acc_layout.addWidget(self.account_status)
        btns = QHBoxLayout()
        b_login = QPushButton("Se connecter")
        b_login.clicked.connect(self.connect_account)
        b_logout = QPushButton("Se déconnecter")
        b_logout.clicked.connect(self.disconnect_account)
        btns.addWidget(b_login)
        btns.addWidget(b_logout)
        btns.addStretch()
        acc_layout.addLayout(btns)
        root.addWidget(acc_box)

        # --- Configuration Azure ---
        azure_box = QGroupBox("Configuration Azure (avancé)")
        azure_form = QFormLayout(azure_box)
        self.client_id = QLineEdit()
        self.tenant_id = QLineEdit()
        azure_form.addRow("Client ID :", self.client_id)
        azure_form.addRow("Tenant ID :", self.tenant_id)
        root.addWidget(azure_box)

        # --- Envoi ---
        envoi_box = QGroupBox("Envoi")
        envoi_layout = QVBoxLayout(envoi_box)
        self.prevent_sleep = QCheckBox(
            "Empêcher la mise en veille du PC pendant un envoi en cours")
        envoi_layout.addWidget(self.prevent_sleep)
        hint_sleep = QLabel("L'ordinateur reste actif tant qu'une campagne tourne "
                            "(l'écran peut s'éteindre). La cadence et les autres "
                            "réglages anti-spam sont dans l'onglet « Délivrabilité ».")
        hint_sleep.setStyleSheet("color:#595959;")
        hint_sleep.setWordWrap(True)
        envoi_layout.addWidget(hint_sleep)
        root.addWidget(envoi_box)

        # --- Contenu par defaut ---
        cont_box = QGroupBox("Contenu par défaut")
        cont_form = QFormLayout(cont_box)
        self.default_subject = QLineEdit()
        self.greeting_fallback = QLineEdit()
        self.closings = QPlainTextEdit()
        self.closings.setMaximumHeight(120)
        self.closings.setPlaceholderText("Une formule de politesse par ligne")
        self.signature = QPlainTextEdit()
        self.signature.setMaximumHeight(90)
        self.signature.setPlaceholderText("Signature (vide = aucune). Une ligne = un saut de ligne.")
        cont_form.addRow("Objet par défaut :", self.default_subject)
        cont_form.addRow("Salutation si genre absent :", self.greeting_fallback)
        cont_form.addRow("Formules de politesse :", self.closings)
        cont_form.addRow("Signature par défaut :", self.signature)
        root.addWidget(cont_box)

        b_save = QPushButton("Enregistrer les paramètres")
        b_save.setMinimumHeight(38)
        b_save.clicked.connect(self.save)
        root.addWidget(b_save)
        root.addStretch()

    def _load(self):
        s = self.mw.settings
        self.client_id.setText(s.get("client_id", ""))
        self.tenant_id.setText(s.get("tenant_id", "common"))
        self.prevent_sleep.setChecked(bool(s.get("prevent_sleep", True)))
        self.default_subject.setText(s.get("default_subject", ""))
        self.greeting_fallback.setText(s.get("greeting_fallback", "Bonjour,"))
        self.closings.setPlainText("\n".join(s.get("closing_salutations", [])))
        self.signature.setPlainText(s.get("signature_html", ""))
        self._refresh_status()

    def on_show(self):
        self._refresh_status()

    def _refresh_status(self):
        try:
            info = self.mw.graph.signed_in_user()
        except Exception:
            info = None
        if info and info[1]:
            self.account_status.setText(f"Connecté : {info[0] or ''} <{info[1]}>")
            self.account_status.setStyleSheet("color:#176d2c; font-weight:bold;")
        else:
            self.account_status.setText("Non connecté.")
            self.account_status.setStyleSheet("color:#b00020; font-weight:bold;")

    def connect_account(self):
        try:
            self.mw.graph.get_token_interactive()
        except Exception as e:
            QMessageBox.critical(self, "Connexion", f"Echec de connexion :\n{e}")
            return
        self._refresh_status()
        self.mw.refresh_account_status()

    def disconnect_account(self):
        self.mw.graph.sign_out()
        self._refresh_status()
        self.mw.refresh_account_status()

    def save(self):
        s = self.mw.settings
        closings = [l.strip() for l in self.closings.toPlainText().splitlines() if l.strip()]
        azure_changed = (self.client_id.text().strip() != s.get("client_id") or
                         self.tenant_id.text().strip() != s.get("tenant_id"))
        s.update({
            "client_id": self.client_id.text().strip(),
            "tenant_id": self.tenant_id.text().strip() or "common",
            "prevent_sleep": self.prevent_sleep.isChecked(),
            "default_subject": self.default_subject.text().strip(),
            "greeting_fallback": self.greeting_fallback.text().strip() or "Bonjour,",
            "closing_salutations": closings or ["Cordialement,"],
            "signature_html": self.signature.toPlainText().strip(),
        })
        s.save()
        if azure_changed:
            self.mw.rebuild_graph_client()
            self._refresh_status()
        QMessageBox.information(self, "Parametres", "Parametres enregistres.")
