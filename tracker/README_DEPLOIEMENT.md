# Tracker d'ouverture - déploiement Cloudflare Worker

Endpoint qui sert le pixel invisible et enregistre les ouvertures de mails.
Gratuit (offre Free de Cloudflare Workers + D1), toujours en ligne, rien à maintenir.

## Prérequis

- Un compte Cloudflare (le domaine `castignac.com` n'a PAS besoin d'y être géré,
  mais c'est plus simple si le DNS est chez Cloudflare).
- Node.js installé.

## 1. Installer Wrangler

```bash
npm install -g wrangler
wrangler login
```

## 2. Créer la base D1

```bash
cd tracker
wrangler d1 create castignac-tracker
```

La commande affiche un `database_id`. Copie-le dans `wrangler.toml`
(remplace `REMPLACER_PAR_ID_D1`).

Puis crée la table :

```bash
wrangler d1 execute castignac-tracker --remote --file=schema.sql
```

## 3. Définir la clé de lecture des statistiques

Génère une clé longue aléatoire (par ex. 40 caractères) et mets-la dans
`wrangler.toml` à la place de `REMPLACER_PAR_UNE_CLE_LONGUE_ALEATOIRE`.

Plus sûr (recommandé) : au lieu de la mettre en clair, utilise un secret et
retire la ligne `STATS_KEY` du bloc `[vars]` :

```bash
wrangler secret put STATS_KEY
```

C'est cette même clé que tu renseigneras dans l'application (onglet réglages).

## 4. Déployer

```bash
wrangler deploy
```

## 5. Sous-domaine `track.castignac.com`

Le bloc `routes` de `wrangler.toml` mappe le Worker sur `track.castignac.com`.

- Si le DNS de `castignac.com` est chez Cloudflare : le custom domain se crée
  automatiquement au `deploy`. Sinon, ajoute chez ton registrar un enregistrement
  CNAME `track` pointant vers la cible indiquée par Cloudflare.
- Tant que le sous-domaine n'est pas prêt : commente le bloc `routes` et utilise
  l'URL par défaut `https://castignac-tracker.<ton-compte>.workers.dev`.

Utiliser un sous-domaine de `castignac.com` (déjà authentifié SPF/DKIM/DMARC)
est meilleur pour la délivrabilité qu'une URL `*.workers.dev`.

## 6. Vérifier

```bash
# doit répondre {"ok":true,...}
curl https://track.castignac.com/health

# simule une ouverture (renvoie un GIF 1x1)
curl https://track.castignac.com/o/test-123 -o pixel.gif

# lit les stats (remplace CLE)
curl "https://track.castignac.com/stats?key=CLE"
```

## 7. Renseigner l'application

Dans SPAM > onglet réglages (Délivrabilité), coche « Activer le suivi
d'ouverture » et renseigne :

- URL du tracker : `https://track.castignac.com`
- Clé statistiques : la clé définie à l'étape 3

## Limites à garder en tête

- Une ouverture n'est comptée que si le client charge les images. Beaucoup de
  clients les bloquent par défaut : un mail ouvert peut ne pas être compté.
- Gmail passe par un proxy d'images (préchargement) : cela peut déclencher une
  « ouverture » dès la réception, sans action réelle du destinataire.
- On ne peut PAS savoir si un mail est tombé en spam ; le pixel indique
  seulement qu'il a été ouvert (donc au moins délivré et consulté).
