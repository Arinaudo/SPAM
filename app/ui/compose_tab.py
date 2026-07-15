"""
Onglet Composer : objet du mail, editeur (mode simple WYSIWYG ou mode HTML
avance), gestion des images inline (cid) et apercu.
"""

import re
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextCharFormat, QTextDocument, QTextListFormat, QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QStackedWidget, QTextBrowser, QTextEdit, QToolBar,
    QVBoxLayout, QWidget, QLineEdit, QGroupBox,
)

from ..config import ASSETS_DIR, resource_dir
from ..core import personalize
from ..core import templates_store


def load_default_template() -> str:
    p = resource_dir() / "default_template.html"
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ("<html><body>__INVISIBLE_REF__<div>__GREETING__<br>"
                "__BODY__<br>__CLOSING__</div></body></html>")


def extract_body_fragment(qt_html: str) -> str:
    """Extrait le contenu interne du <body> du HTML genere par Qt."""
    m = re.search(r"<body[^>]*>(.*)</body>", qt_html, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else qt_html


class RichEditor(QTextEdit):
    """Editeur de texte riche, avec insertion d'images en reference cid."""

    def __init__(self, images_registry: dict, parent=None):
        super().__init__(parent)
        self.images = images_registry  # dict partage {cid: chemin}
        self.setAcceptRichText(True)
        self.setMinimumHeight(200)
        f = QFont("Calibri", 11)
        self.setFont(f)

    def insert_image_cid(self, cid: str, path: str):
        """Insere une image (deja enregistree) a la position du curseur."""
        img = QImage(path)
        if img.isNull():
            return
        url = QUrl(f"cid:{cid}")
        self.document().addResource(QTextDocument.ImageResource, url, img)
        cursor = self.textCursor()
        # largeur max raisonnable pour l'apercu
        from PySide6.QtGui import QTextImageFormat
        fmt = QTextImageFormat()
        fmt.setName(f"cid:{cid}")
        if img.width() > 680:
            fmt.setWidth(680)
        cursor.insertImage(fmt)
        self.setTextCursor(cursor)


class ComposeTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.images = {}   # {cid: chemin_fichier} pour cette campagne
        self.attachments = []  # [chemins] pieces jointes (PDF/XLSX/DOCX...)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        # Onglet défilable : tout reste accessible même sur petit écran (Mac).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        root = QVBoxLayout(inner)

        # Objet
        subj_row = QHBoxLayout()
        subj_row.addWidget(QLabel("Objet :"))
        self.subject_edit = QLineEdit(self.mw.settings.get("default_subject", ""))
        subj_row.addWidget(self.subject_edit)
        root.addLayout(subj_row)

        # Bascule de mode
        mode_row = QHBoxLayout()
        self.html_mode = QCheckBox("Mode HTML avancé (éditer le code du mail)")
        self.html_mode.stateChanged.connect(self._toggle_mode)
        mode_row.addWidget(self.html_mode)
        mode_row.addStretch()
        hint = QLabel("Champs de fusion : {PRENOM} {NOM} {SOCIETE} {EMAIL}")
        hint.setStyleSheet("color:#666;")
        mode_row.addWidget(hint)
        root.addLayout(mode_row)

        # Salutations & formules de politesse propres a cette campagne
        s = self.mw.settings
        sal_box = QGroupBox("Salutations & politesse de cette campagne")
        sal_v = QVBoxLayout(sal_box)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Si Monsieur :"))
        self.greet_monsieur = QLineEdit(s.get("greeting_monsieur", "Bonjour Monsieur,"))
        row1.addWidget(self.greet_monsieur)
        row1.addWidget(QLabel("Si Madame :"))
        self.greet_madame = QLineEdit(s.get("greeting_madame", "Bonjour Madame,"))
        row1.addWidget(self.greet_madame)
        row1.addWidget(QLabel("Si genre absent :"))
        self.greet_fallback = QLineEdit(s.get("greeting_fallback", "Bonjour,"))
        row1.addWidget(self.greet_fallback)
        sal_v.addLayout(row1)
        sal_v.addWidget(QLabel(
            "Formules de politesse (placeholder __CLOSING__, une par ligne, "
            "tiree au hasard pour chaque mail) :"))
        self.closings_edit = QPlainTextEdit()
        self.closings_edit.setMaximumHeight(80)
        self.closings_edit.setPlainText("\n".join(s.get("closing_salutations", [])))
        sal_v.addWidget(self.closings_edit)
        sal_v.addWidget(QLabel(
            "Signature en bas du mail (une ligne = un saut de ligne ; "
            "laisser vide pour aucune signature) :"))
        self.signature_edit = QPlainTextEdit()
        self.signature_edit.setMaximumHeight(60)
        self.signature_edit.setPlainText(s.get("signature_html", ""))
        sal_v.addWidget(self.signature_edit)
        root.addWidget(sal_box)

        # Barre d'outils (mode simple)
        self.toolbar = QToolBar()
        self._build_toolbar()
        root.addWidget(self.toolbar)

        # Editeurs empiles
        self.stack = QStackedWidget()
        self.rich = RichEditor(self.images)
        self.html = QPlainTextEdit()
        self.html.setPlaceholderText("Code HTML complet du mail "
                                     "(placeholders : __GREETING__, __CLOSING__, "
                                     "__INVISIBLE_REF__, champs {PRENOM}...).")
        self.stack.addWidget(self.rich)   # index 0
        self.stack.addWidget(self.html)   # index 1
        root.addWidget(self.stack, 1)

        # Panneau images + actions
        bottom = QHBoxLayout()

        # Hauteurs communes pour que les deux cadres soient identiques.
        LIST_H = 120
        HINT_H = 18

        img_box = QGroupBox("Images inline (jointes au mail)")
        img_layout = QVBoxLayout(img_box)
        self.img_list = QListWidget()
        self.img_list.setFixedHeight(LIST_H)
        img_layout.addWidget(self.img_list)
        img_btns = QHBoxLayout()
        b_add = QPushButton("Ajouter une image")
        b_add.clicked.connect(self.add_image)
        b_copy = QPushButton("Copier la balise <img>")
        b_copy.clicked.connect(self.copy_img_tag)
        b_del = QPushButton("Retirer")
        b_del.clicked.connect(self.remove_image)
        img_btns.addWidget(b_add)
        img_btns.addWidget(b_copy)
        img_btns.addWidget(b_del)
        img_layout.addLayout(img_btns)
        self.img_hint = QLabel("Images affichées dans le corps du mail.")
        self.img_hint.setStyleSheet("color:#666;")
        self.img_hint.setFixedHeight(HINT_H)
        img_layout.addWidget(self.img_hint)
        bottom.addWidget(img_box, 1)

        # Pieces jointes (documents : PDF, XLSX, DOCX...)
        att_box = QGroupBox("Documents joints (PDF, Excel, Word...)")
        att_layout = QVBoxLayout(att_box)
        self.att_list = QListWidget()
        self.att_list.setFixedHeight(LIST_H)
        att_layout.addWidget(self.att_list)
        att_btns = QHBoxLayout()
        b_att_add = QPushButton("Ajouter un document")
        b_att_add.clicked.connect(self.add_attachment)
        b_att_del = QPushButton("Retirer")
        b_att_del.clicked.connect(self.remove_attachment)
        att_btns.addWidget(b_att_add)
        att_btns.addWidget(b_att_del)
        att_layout.addLayout(att_btns)
        self.att_size_label = QLabel("Aucun document joint.")
        self.att_size_label.setStyleSheet("color:#666;")
        self.att_size_label.setFixedHeight(HINT_H)
        att_layout.addWidget(self.att_size_label)
        bottom.addWidget(att_box, 1)

        act_box = QVBoxLayout()
        b_preview = QPushButton("Aperçu du mail")
        b_preview.clicked.connect(self.preview)
        b_preview.setMinimumHeight(40)
        act_box.addWidget(b_preview)
        b_test = QPushButton("Envoyer un test")
        b_test.clicked.connect(self.send_test)
        b_test.setMinimumHeight(40)
        b_test.setStyleSheet(
            "QPushButton { background-color:#0d6efd; color:#ffffff; font-weight:bold;"
            " border:none; border-radius:4px; padding:6px 12px; }")
        act_box.addWidget(b_test)
        b_loadtpl = QPushButton("Charger le modèle HTML par défaut")
        b_loadtpl.clicked.connect(self.load_default_into_html)
        act_box.addWidget(b_loadtpl)

        act_box.addSpacing(8)
        b_save_tpl = QPushButton("Enregistrer comme modèle")
        b_save_tpl.clicked.connect(self.save_as_template)
        act_box.addWidget(b_save_tpl)
        b_load_tpl = QPushButton("Charger un modèle")
        b_load_tpl.clicked.connect(self.load_template)
        act_box.addWidget(b_load_tpl)
        b_del_tpl = QPushButton("Supprimer un modèle")
        b_del_tpl.clicked.connect(self.delete_template)
        act_box.addWidget(b_del_tpl)

        act_box.addStretch()
        bottom.addLayout(act_box)

        root.addLayout(bottom)

    def _build_toolbar(self):
        def act(text, slot):
            a = self.toolbar.addAction(text)
            a.triggered.connect(slot)
            return a

        act("Gras", lambda: self._toggle_fmt("bold"))
        act("Italique", lambda: self._toggle_fmt("italic"))
        act("Souligne", lambda: self._toggle_fmt("underline"))
        self.toolbar.addSeparator()
        act("Titre", self._make_heading)
        act("Liste", self._make_list)
        self.toolbar.addSeparator()
        act("Lien", self._insert_link)
        act("Image", self.add_image)

    # ------------------------------------------------------------------
    # Mode simple / HTML
    # ------------------------------------------------------------------
    def _toggle_mode(self):
        if self.html_mode.isChecked():
            # bascule simple -> HTML : on genere le HTML complet une fois
            if not self.html.toPlainText().strip():
                self.html.setPlainText(self._build_full_html_from_simple())
            self.stack.setCurrentIndex(1)
            self.toolbar.setDisabled(True)
        else:
            self.stack.setCurrentIndex(0)
            self.toolbar.setDisabled(False)

    def _toggle_fmt(self, kind):
        fmt = QTextCharFormat()
        cur = self.rich.currentCharFormat()
        if kind == "bold":
            fmt.setFontWeight(QFont.Normal if cur.fontWeight() > QFont.Normal else QFont.Bold)
        elif kind == "italic":
            fmt.setFontItalic(not cur.fontItalic())
        elif kind == "underline":
            fmt.setFontUnderline(not cur.fontUnderline())
        self.rich.mergeCurrentCharFormat(fmt)

    def _make_heading(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmt.setFontPointSize(13)
        fmt.setForeground(Qt.GlobalColor.darkBlue)
        self.rich.mergeCurrentCharFormat(fmt)

    def _make_list(self):
        cursor = self.rich.textCursor()
        cursor.createList(QTextListFormat.ListDisc)

    def _insert_link(self):
        url, ok = QInputDialog.getText(self, "Inserer un lien", "URL (https://...) :")
        if not ok or not url.strip():
            return
        text, ok2 = QInputDialog.getText(self, "Texte du lien", "Texte affiche :", text=url)
        if not ok2:
            text = url
        cursor = self.rich.textCursor()
        cursor.insertHtml(f'<a href="{url.strip()}">{text.strip()}</a> ')

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp)")
        if not path:
            return
        ext = Path(path).suffix.lower()
        cid = "img" + uuid.uuid4().hex[:8]
        dest = ASSETS_DIR / f"{cid}{ext}"
        try:
            shutil.copy2(path, dest)
        except Exception as e:
            QMessageBox.warning(self, "Image", f"Copie impossible : {e}")
            return
        self.images[cid] = str(dest)
        item = QListWidgetItem(f"{cid}  —  {Path(path).name}")
        item.setData(Qt.UserRole, cid)
        self.img_list.addItem(item)
        # En mode simple : insertion directe dans l'editeur
        if not self.html_mode.isChecked():
            self.rich.insert_image_cid(cid, str(dest))

    def copy_img_tag(self):
        item = self.img_list.currentItem()
        if not item:
            if self.img_list.count() == 0:
                QMessageBox.information(
                    self, "Aucune image",
                    "Ajoutez d'abord une image avec « Ajouter une image », "
                    "puis selectionnez-la dans la liste.")
            else:
                QMessageBox.information(
                    self, "Aucune image selectionnee",
                    "Selectionnez d'abord une image dans la liste, "
                    "puis cliquez sur « Copier la balise <img> ».")
            return
        cid = item.data(Qt.UserRole)
        tag = f'<img src="cid:{cid}" style="max-width:680px;">'
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(tag)
        QMessageBox.information(self, "Copie", "Balise <img> copiee dans le presse-papiers.")

    def remove_image(self):
        item = self.img_list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        self.images.pop(cid, None)
        self.img_list.takeItem(self.img_list.row(item))

    # ------------------------------------------------------------------
    # Documents joints (PDF / XLSX / DOCX ...)
    # ------------------------------------------------------------------
    def _fmt_size(self, nbytes: int) -> str:
        mo = nbytes / (1024 * 1024)
        return f"{mo:.1f} Mo" if mo >= 0.1 else f"{nbytes // 1024} Ko"

    def _refresh_att_size(self):
        total = personalize.attachments_total_bytes(self.attachments)
        if not self.attachments:
            self.att_size_label.setStyleSheet("color:#666;")
            self.att_size_label.setText("Aucun document joint.")
            return
        txt = f"Total joint : {self._fmt_size(total)}"
        # Graph accepte ~3 Mo par mail en un seul appel ; au-dela on alerte.
        if total > 3 * 1024 * 1024:
            txt += "  ⚠️ Volumineux : risque de rejet et de spam. Préférez un lien."
            self.att_size_label.setStyleSheet("color:#b00020;")
        else:
            self.att_size_label.setStyleSheet("color:#666;")
        self.att_size_label.setText(txt)

    def add_attachment(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choisir un ou plusieurs documents", "",
            "Documents (*.pdf *.xlsx *.xls *.docx *.doc *.pptx *.csv *.txt *.zip);;"
            "Tous les fichiers (*.*)")
        if not paths:
            return
        for path in paths:
            ext = Path(path).suffix.lower()
            dest = ASSETS_DIR / f"att_{uuid.uuid4().hex[:8]}{ext}"
            try:
                shutil.copy2(path, dest)
            except Exception as e:
                QMessageBox.warning(self, "Document", f"Copie impossible : {e}")
                continue
            self.attachments.append(str(dest))
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, str(dest))
            self.att_list.addItem(item)
        self._refresh_att_size()

    def remove_attachment(self):
        item = self.att_list.currentItem()
        if not item:
            return
        path = item.data(Qt.UserRole)
        if path in self.attachments:
            self.attachments.remove(path)
        self.att_list.takeItem(self.att_list.row(item))
        self._refresh_att_size()

    def get_attachments(self) -> list:
        return list(self.attachments)

    # ------------------------------------------------------------------
    # Construction du HTML final
    # ------------------------------------------------------------------
    def _build_full_html_from_simple(self) -> str:
        fragment = extract_body_fragment(self.rich.toHtml())
        template = load_default_template()
        return template.replace("__BODY__", fragment)

    def get_full_html(self) -> str:
        if self.html_mode.isChecked():
            return self.html.toPlainText()
        return self._build_full_html_from_simple()

    def get_subject(self) -> str:
        return self.subject_edit.text().strip()

    def get_images(self) -> dict:
        return dict(self.images)

    def get_greetings(self) -> dict:
        return {
            "greeting_monsieur": self.greet_monsieur.text().strip(),
            "greeting_madame": self.greet_madame.text().strip(),
            "greeting_fallback": self.greet_fallback.text().strip(),
        }

    def get_closings(self) -> list:
        return [l.strip() for l in self.closings_edit.toPlainText().splitlines()
                if l.strip()]

    def get_signature(self) -> str:
        return self.signature_edit.toPlainText().strip()

    def _overrides(self) -> dict:
        ov = self.get_greetings()
        ov["closing_salutations"] = self.get_closings()
        ov["signature_html"] = self.get_signature()
        return ov

    def load_default_into_html(self):
        self.html_mode.setChecked(True)
        self.html.setPlainText(self._build_full_html_from_simple()
                               if extract_body_fragment(self.rich.toHtml()).strip()
                               else load_default_template().replace("__BODY__",
                               "<p>Votre texte ici...</p>"))

    # ------------------------------------------------------------------
    # Modèles de mail / chargement de contenu
    # ------------------------------------------------------------------
    def load_content(self, subject, html, images, greetings, closings, signature,
                     attachments=None):
        """Charge un mail complet dans le Composer (mode HTML avancé)."""
        self.subject_edit.setText(subject or "")
        # Images
        self.images.clear()
        self.img_list.clear()
        for cid, path in (images or {}).items():
            self.images[cid] = path
            item = QListWidgetItem(f"{cid}  —  {Path(path).name}")
            item.setData(Qt.UserRole, cid)
            self.img_list.addItem(item)
        # Documents joints
        self.attachments = []
        self.att_list.clear()
        for path in (attachments or []):
            self.attachments.append(path)
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            self.att_list.addItem(item)
        self._refresh_att_size()
        # Salutations / politesse / signature
        g = greetings or {}
        self.greet_monsieur.setText(g.get("greeting_monsieur", ""))
        self.greet_madame.setText(g.get("greeting_madame", ""))
        self.greet_fallback.setText(g.get("greeting_fallback", ""))
        self.closings_edit.setPlainText("\n".join(closings or []))
        self.signature_edit.setPlainText(signature or "")
        # Corps : on passe en mode HTML avancé avec le HTML fourni
        self.html.setPlainText(html or "")
        self.html_mode.setChecked(True)

    def save_as_template(self):
        err = self.validate()
        if err:
            QMessageBox.warning(self, "Modèle", err)
            return
        name, ok = QInputDialog.getText(
            self, "Enregistrer le modèle", "Nom du modèle :")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in templates_store.template_names():
            r = QMessageBox.question(
                self, "Modèle existant",
                f"Un modèle « {name} » existe déjà. Le remplacer ?")
            if r != QMessageBox.Yes:
                return
        templates_store.save_template(name, {
            "subject": self.get_subject(),
            "body_html": self.get_full_html(),
            "images": self.get_images(),
            "greetings": self.get_greetings(),
            "closings": self.get_closings(),
            "signature": self.get_signature(),
        })
        QMessageBox.information(self, "Modèle", f"Modèle « {name} » enregistré.")

    def load_template(self):
        names = templates_store.template_names()
        if not names:
            QMessageBox.information(self, "Modèles", "Aucun modèle enregistré.")
            return
        name, ok = QInputDialog.getItem(
            self, "Charger un modèle", "Modèle :", names, 0, False)
        if not ok or not name:
            return
        data = templates_store.get_template(name)
        if not data:
            return
        self.load_content(data.get("subject"), data.get("body_html"),
                          data.get("images"), data.get("greetings"),
                          data.get("closings"), data.get("signature"))
        QMessageBox.information(self, "Modèle", f"Modèle « {name} » chargé.")

    def delete_template(self):
        names = templates_store.template_names()
        if not names:
            QMessageBox.information(self, "Modèles", "Aucun modèle enregistré.")
            return
        name, ok = QInputDialog.getItem(
            self, "Supprimer un modèle", "Modèle :", names, 0, False)
        if not ok or not name:
            return
        r = QMessageBox.question(self, "Supprimer", f"Supprimer le modèle « {name} » ?")
        if r == QMessageBox.Yes:
            templates_store.delete_template(name)
            QMessageBox.information(self, "Modèle", f"Modèle « {name} » supprimé.")

    # ------------------------------------------------------------------
    def preview(self):
        html = self.get_full_html()
        sample = {"genre": "Monsieur", "prenom": "Jean", "nom": "Dupont",
                  "societe": "Exemple SARL", "email": "jean.dupont@exemple.fr"}
        rendered = personalize.render_body(html, sample, self.mw.settings,
                                           ref="ref:apercu", overrides=self._overrides())
        dlg = QDialog(self)
        dlg.setWindowTitle("Aperçu du mail (exemple : Monsieur Jean Dupont)")
        dlg.resize(780, 640)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        # enregistre les images pour l'apercu
        for cid, path in self.images.items():
            img = QImage(path)
            if not img.isNull():
                browser.document().addResource(
                    QTextDocument.ImageResource, QUrl(f"cid:{cid}"), img)
        browser.setHtml(rendered)
        lay.addWidget(browser)
        info = QLabel(f"Objet : {self.get_subject() or '(vide)'}")
        info.setStyleSheet("font-weight:bold; padding:4px;")
        lay.addWidget(info)
        dlg.exec()

    def send_test(self):
        """Envoie le mail en cours a une adresse de test via Outlook."""
        err = self.validate()
        if err:
            QMessageBox.warning(self, "Composer", err)
            return

        # Connexion si necessaire (interactive sur le thread principal)
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

        info = self.mw.graph.signed_in_user()
        default_to = info[1] if info and info[1] else ""
        to, ok = QInputDialog.getText(
            self, "Envoyer un test",
            "Adresse de test (vous recevrez ce mail) :", text=default_to)
        if not ok or not to.strip():
            return
        to = to.strip()

        token = self.mw.graph.get_token_silent()
        if not token:
            QMessageBox.critical(self, "Connexion", "Connexion Outlook perdue.")
            return

        html = self.get_full_html()
        sample = {"genre": "", "prenom": "", "nom": "", "societe": "", "email": to}
        rendered = personalize.render_body(
            html, sample, self.mw.settings, overrides=self._overrides())
        images = personalize.collect_inline_images(rendered, self.images)
        file_attachments = personalize.collect_file_attachments(self.attachments)
        subject = "[TEST] " + (self.get_subject() or "(sans objet)")
        try:
            self.mw.graph.send_mail(token, to, subject, rendered,
                                    inline_images=images, ref=None,
                                    save_to_sent=False,
                                    file_attachments=file_attachments)
            QMessageBox.information(
                self, "Test envoyé",
                f"Mail de test envoyé à {to}.\nVérifiez votre boîte de réception.")
        except Exception as e:
            QMessageBox.critical(self, "Envoi du test", f"Échec : {e}")

    def validate(self) -> str:
        """Retourne un message d'erreur, ou '' si OK."""
        if not self.get_subject():
            return "L'objet du mail est vide."
        html = self.get_full_html()
        if not re.sub(r"<[^>]+>", "", html).strip():
            return "Le corps du mail est vide."
        return ""
