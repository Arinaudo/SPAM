"""
Suivi d'ouverture par pixel invisible.

Principe
--------
On insere dans le HTML de chaque mail une image 1x1 transparente pointant vers
un endpoint Cloudflare Worker (ex. https://track.castignac.com/o/<token>).
Quand le destinataire ouvre le mail, son client charge l'image : le Worker
enregistre l'ouverture (date, IP, User-Agent) dans une base D1.

L'application recupere ensuite ces ouvertures via l'endpoint /stats (protege
par une cle) et met a jour les colonnes open_count / opened_at des destinataires.

Le "token" est le meme identifiant unique que le "ref" anti-spam deja present
sur chaque mail, sans le prefixe "ref:".

Limites
-------
- Une ouverture n'est comptee que si le client charge les images (souvent
  bloquees par defaut). Un non-comptage ne signifie donc PAS "tombe en spam".
- Gmail precharge les images via un proxy : une "ouverture" peut apparaitre
  des la reception.
"""

import requests

# Pixel : display:none + 1px + opacity 0. Volontairement discret.
PIXEL_TAG = (
    '<img src="{url}" width="1" height="1" alt="" border="0" '
    'style="display:none !important;width:1px;height:1px;max-height:1px;'
    'max-width:1px;opacity:0;overflow:hidden;line-height:0;font-size:0;" />'
)


def token_from_ref(ref: str) -> str:
    """Deduit le token URL-safe a partir du ref.

    "ref:20260707-abcd"  ->  "20260707-abcd"
    """
    if not ref:
        return ""
    return ref.split("ref:", 1)[-1].strip()


def ref_from_token(token: str) -> str:
    """Operation inverse : reconstruit le ref stocke en base a partir du token."""
    token = (token or "").strip()
    return f"ref:{token}" if token else ""


def pixel_url(base_url: str, token: str) -> str:
    """URL complete du pixel. Extension .png ajoutee pour faire 'vraie image'."""
    base = (base_url or "").rstrip("/")
    return f"{base}/o/{token}.png"


def inject_pixel(html: str, base_url: str, token: str) -> str:
    """Insere le pixel juste avant </body> (ou en fin de HTML si absent).

    Ne fait rien si base_url ou token est vide (retourne le HTML inchange).
    """
    if not base_url or not token:
        return html
    tag = PIXEL_TAG.format(url=pixel_url(base_url, token))
    idx = html.lower().rfind("</body>")
    if idx != -1:
        return html[:idx] + tag + html[idx:]
    return html + tag


def fetch_opens(base_url: str, api_key: str, since: str = "", timeout: int = 30):
    """Recupere les ouvertures agregees depuis le Worker.

    Retourne une liste de dicts : {token, first_open, last_open, count}.
    Leve une exception (requests / ValueError) en cas d'echec reseau ou
    d'authentification (401).
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise ValueError("URL du tracker non configuree.")
    params = {"key": api_key or ""}
    if since:
        params["since"] = since
    r = requests.get(f"{base}/stats", params=params, timeout=timeout)
    if r.status_code == 401:
        raise ValueError("Cle statistiques invalide (401).")
    r.raise_for_status()
    data = r.json()
    return data.get("opens", [])


def health_ok(base_url: str, timeout: int = 15) -> bool:
    """Verifie que le Worker repond (utile pour un bouton 'Tester la connexion')."""
    base = (base_url or "").rstrip("/")
    if not base:
        return False
    try:
        r = requests.get(f"{base}/health", timeout=timeout)
        return r.status_code == 200 and bool(r.json().get("ok"))
    except Exception:
        return False
