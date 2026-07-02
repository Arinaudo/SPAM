"""
Personnalisation du mail : civilite (Monsieur/Madame), formule de politesse
aleatoire, reference invisible anti-spam, fusion des champs ({PRENOM}, {NOM},
{SOCIETE}, {EMAIL}) et collecte des images inline (cid).
"""

import datetime
import random
import re
import secrets

from .graph_client import file_to_b64


def build_greeting(genre: str, fallback: str = "Bonjour,",
                   monsieur: str = "Bonjour Monsieur,",
                   madame: str = "Bonjour Madame,") -> str:
    g = (genre or "").strip().lower()
    if g in ("monsieur", "m", "mr", "m.", "homme"):
        return monsieur
    if g in ("madame", "mme", "mrs", "mme.", "femme"):
        return madame
    return fallback


def build_closing(salutations) -> str:
    if not salutations:
        return "Cordialement,"
    return random.choice(salutations)


def build_invisible_ref() -> str:
    token = secrets.token_hex(6)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"ref:{ts}-{token}"


def merge_fields(html: str, recipient: dict) -> str:
    """Remplace {PRENOM}, {NOM}, {SOCIETE}, {EMAIL} (insensible a la casse)."""
    repl = {
        "PRENOM": recipient.get("prenom", ""),
        "NOM": recipient.get("nom", ""),
        "SOCIETE": recipient.get("societe", ""),
        "EMAIL": recipient.get("email", ""),
    }

    def _sub(m):
        key = m.group(1).upper()
        return repl.get(key, m.group(0))

    return re.sub(r"\{(\w+)\}", _sub, html)


def render_body(template_html: str, recipient: dict, settings, ref: str = None,
                overrides: dict = None) -> str:
    """
    Produit le HTML final personnalise pour un destinataire.

    Placeholders supportes dans le template :
      __GREETING__       -> Bonjour Monsieur/Madame, (selon GENRE)
      __CLOSING__        -> formule de politesse aleatoire
      __INVISIBLE_REF__  -> commentaire HTML unique (anti-spam)
    + fusion {PRENOM}, {NOM}, {SOCIETE}, {EMAIL}.

    `overrides` (optionnel) permet de definir les salutations/politesses
    PROPRES A UNE CAMPAGNE ; sinon on retombe sur les valeurs des parametres.
    Cles supportees : greeting_monsieur, greeting_madame, greeting_fallback,
    closing_salutations.
    """
    cfg = overrides or {}

    def _pick(key, default):
        v = cfg.get(key)
        return v if v else settings.get(key, default)

    greeting = build_greeting(
        recipient.get("genre", ""),
        fallback=_pick("greeting_fallback", "Bonjour,"),
        monsieur=_pick("greeting_monsieur", "Bonjour Monsieur,"),
        madame=_pick("greeting_madame", "Bonjour Madame,"))
    closings = cfg.get("closing_salutations")
    if not closings:
        closings = settings.get("closing_salutations", [])
    closing = build_closing(closings)
    ref = ref or build_invisible_ref()

    # Signature : valeur de la campagne si fournie (meme vide = pas de signature),
    # sinon valeur des parametres. Les sauts de ligne deviennent des <br>.
    if "signature_html" in cfg:
        signature = cfg.get("signature_html") or ""
    else:
        signature = settings.get("signature_html", "")
    sig_block = ("<p>" + signature.strip().replace("\n", "<br>\n") + "</p>"
                 if signature.strip() else "")

    html = template_html
    html = html.replace("__GREETING__", greeting)
    html = html.replace("__CLOSING__", closing)
    html = html.replace("__SIGNATURE__", sig_block)
    html = html.replace("__INVISIBLE_REF__", f"<!-- {ref} -->")
    html = merge_fields(html, recipient)
    return html


# ----------------------------------------------------------------------------
# Images inline (cid)
# ----------------------------------------------------------------------------

CID_RE = re.compile(r'src=["\']cid:([^"\']+)["\']', re.IGNORECASE)


def _content_type_for(path: str) -> str:
    p = path.lower()
    if p.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if p.endswith(".gif"):
        return "image/gif"
    if p.endswith(".webp"):
        return "image/webp"
    return "image/png"


def collect_inline_images(html: str, cid_to_path: dict):
    """
    Repere les images referencees dans le HTML (src="cid:XXX") et construit la
    liste d'attachements inline a partir du registre {cid: chemin_fichier}.
    Seules les images effectivement utilisees dans le HTML sont jointes.
    """
    used = set(CID_RE.findall(html or ""))
    images = []
    for cid in used:
        path = cid_to_path.get(cid)
        if not path:
            continue
        try:
            images.append({
                "cid": cid,
                "name": f"{cid}",
                "content_type": _content_type_for(path),
                "b64": file_to_b64(path),
            })
        except Exception:
            continue
    return images
