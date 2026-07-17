"""
Onglet Mode d'emploi : tutoriel d'utilisation avec des liens internes.

Construit avec le meme style que les autres onglets (zone defilante + encadres
QGroupBox), pour un fond et un cadrage coherents. Un clic sur un lien
(ex. « composer le mail ») bascule vers l'onglet correspondant ; pour le
Composer, le curseur est place pret a ecrire.

Les liens utilisent un schema maison « app:<cible> ». Les QLabel emettent
linkActivated (avec l'URL en texte) ; on delegue la navigation a la fenetre
principale (MainWindow.goto_help_target).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

INTRO = (
    "SPAM envoie vos campagnes directement depuis votre compte Outlook "
    "<b>@castignac.com</b> : on importe une liste, on rédige le mail, on clique "
    "sur Démarrer. Les liens ci-dessous mènent au bon endroit dans l'application."
)

# (titre de l'encadré, contenu HTML avec liens app:)
SECTIONS = [
    ("Avant de commencer",
     "Connectez-vous à Outlook une seule fois dans les "
     "<a href='app:settings'>Paramètres</a>. La connexion est ensuite mémorisée."),

    ("1. Composer le mail",
     "Rédigez l'objet et le message dans <a href='app:compose_write'>Composer</a> "
     "(le curseur arrive prêt dans la zone de texte). La civilité est automatique "
     "(Bonjour Monsieur / Madame) et vous pouvez insérer les champs de fusion "
     "{PRENOM}, {NOM}, {SOCIETE}, {EMAIL}. « Aperçu du mail » et « Envoyer un "
     "test » permettent de contrôler avant un gros envoi.<br><br>"
     "Pièces jointes : encadré « Documents joints » du Composer, bouton "
     "« Ajouter un document » (PDF, Excel, Word...). Restez sous 3 Mo au total ; "
     "au-delà, préférez un lien."),

    ("2. Importer les destinataires",
     "Importez une liste Excel/CSV dans <a href='app:recipients'>Destinataires</a>, "
     "vérifiez l'association des colonnes, puis « Valider cette liste ». Vous "
     "pouvez aussi ajouter un destinataire à la main. Les adresses de la liste "
     "de suppression (bounces / désinscrits) sont automatiquement écartées."),

    ("3. Anti-spam",
     "Avant un envoi en volume, vérifiez l'authentification du domaine "
     "(SPF / DKIM / DMARC) dans <a href='app:delivery'>Anti-spam</a>. Une "
     "bonne authentification limite fortement le classement en spam."),

    ("4. Lancer l'envoi",
     "Dans <a href='app:queue'>Envoi</a> : « Préparer l'envoi », puis "
     "« Démarrer l'envoi ». Un récapitulatif s'affiche avant l'envoi réel. "
     "Pause, reprise ou arrêt possibles ; la progression est enregistrée et "
     "reprenable plus tard."),

    ("Suivre les résultats",
     "L'<a href='app:history'>Historique</a> liste les mails traités, avec les "
     "colonnes Ouvertures et Réponses. Trois boutons les actualisent : "
     "« Rafraîchir les ouvertures », « Rafraîchir les réponses » et « Rafraîchir "
     "les bounces » (adresses mortes vers la liste de suppression). Le "
     "<a href='app:dashboard'>Tableau de bord</a> donne une vue d'ensemble."),

    ("Réglages",
     "Activez le suivi des ouvertures et des réponses dans les "
     "<a href='app:settings'>Paramètres</a> (le suivi des réponses demande une "
     "reconnexion pour lire la boîte)."),
]


class HelpTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        root = QVBoxLayout(inner)

        title = QLabel("Mode d'emploi de SPAM")
        # Pas de couleur imposee : on herite de la couleur de texte du theme
        # (blanc en mode sombre), pour rester lisible dans tous les cas.
        title.setStyleSheet("font-size:18px; font-weight:bold; padding:4px 0;")
        root.addWidget(title)

        root.addWidget(self._label(INTRO))

        for heading, html in SECTIONS:
            box = QGroupBox(heading)
            lay = QVBoxLayout(box)
            lay.addWidget(self._label(html))
            root.addWidget(box)
        root.addStretch()

    def _label(self, html: str) -> QLabel:
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setOpenExternalLinks(False)
        lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        lbl.linkActivated.connect(self._on_link)
        return lbl

    def _on_link(self, href: str):
        if href.startswith("app:"):
            self.mw.goto_help_target(href[4:])
