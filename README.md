# SPAM — Système Pratique pour l'Automatisation des Mails

Application de bureau pour envoyer facilement des campagnes d'emails B2B, en
remplacement d'un logiciel payant. Conçue pour des collègues **non techniques** :
on importe une liste, on rédige le mail, on clique sur Démarrer.

Compatible **Windows et macOS**. Le moteur d'envoi reprend le code Python existant
(Microsoft Graph / Outlook, personnalisation Monsieur/Madame, délais anti-spam).

---

## Fonctionnalités

- **Import de liste** Excel (`.xlsx`) ou CSV, avec détection et association
  automatique des colonnes (EMAIL, GENRE, PRÉNOM, NOM, SOCIÉTÉ). Validation des
  adresses et suppression des doublons.
- **Composition du mail** en deux modes :
  - *Simple* : éditeur visuel (gras, listes, liens, images) ;
  - *HTML avancé* : édition directe du code pour modifier le gabarit.
  - Civilité automatique (Bonjour Monsieur / Madame) selon la colonne GENRE.
  - Champs de fusion : `{PRENOM}`, `{NOM}`, `{SOCIETE}`, `{EMAIL}`.
  - **Images** insérées et envoyées en pièce jointe *inline* (affichage immédiat).
  - **Aperçu** du rendu final.
- **File d'attente** pour les envois longs (30/40 k destinataires) : barre de
  progression, compteurs, **temps restant estimé**, et contrôles
  **Démarrer / Pause / Reprendre / Arrêter**. La progression est sauvegardée :
  on peut fermer l'application et **reprendre plus tard**.
- **Historique** de tous les mails traités (envoyés / en erreur), avec recherche,
  filtre et export CSV.
- **Cadence d'envoi configurable** (par défaut 5–8 s entre deux mails) + référence
  invisible unique par mail pour limiter le classement en spam.

---

## Lancer depuis les sources (test rapide)

Prérequis : Python 3.10+ installé.

```bash
cd CastignacMailer
python -m venv .venv
# Windows :
.venv\Scripts\activate
# macOS :
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

---

## Construire l'exécutable distribuable

> ⚠️ Un exécutable doit être construit **sur le système cible** : le `.exe` se
> fabrique sous Windows, le `.app` sous macOS. On ne peut pas générer l'un depuis
> l'autre.

### Windows
Double-cliquer sur **`build_windows.bat`**.
Résultat : `dist\SPAM.exe` (un seul fichier, à distribuer aux collègues).

### macOS
Dans un terminal :
```bash
chmod +x build_macos.sh
./build_macos.sh
```
Résultat : `dist/SPAM.app`.
Au premier lancement : clic droit sur l'app > **Ouvrir** (pour contourner Gatekeeper).

---

## Première utilisation par un collègue

1. Onglet **Paramètres** > **Se connecter** : une fenêtre Microsoft s'ouvre,
   il se connecte avec son compte `@castignac.com`. La connexion est mémorisée.
2. Onglet **Composer** : saisir l'objet et le texte du mail (+ images).
3. Onglet **Destinataires** : importer la liste, vérifier l'association des colonnes,
   cliquer sur **Valider cette liste**.
4. Onglet **File d'attente** : **Créer depuis Composer + Destinataires**, puis
   **Démarrer l'envoi**. Suivre la progression ; on peut mettre en pause ou arrêter.
5. Onglet **Historique** : consulter les envois passés.

---

## Où sont stockées les données

Base SQLite, paramètres, cache de connexion et images sont dans un dossier
applicatif standard :

- **Windows** : `%APPDATA%\SPAM`
- **macOS** : `~/Library/Application Support/SPAM`

Rien n'est envoyé ailleurs : les envois passent directement par le compte Outlook
du collègue via Microsoft Graph.

---

## Notes importantes

- **Sécurité** : l'ancien `CLIENT_SECRET` présent dans `envoi_emails.py` a été
  retiré (inutile en connexion interactive). Pense à le **révoquer dans Azure**.
- **Délivrabilité** : pour limiter le spam sur de gros volumes, activer **DKIM**
  et **DMARC** sur le domaine `castignac.com`, et ajouter un **lien de
  désinscription** dans le mail (obligation RGPD). Voir `../AUDIT_ET_REPRISE_PROJET.md`.
- **Configuration Azure** : l'app utilise par défaut le Client ID existant
  (permissions `Mail.Send`). Modifiable dans Paramètres > Configuration Azure.
