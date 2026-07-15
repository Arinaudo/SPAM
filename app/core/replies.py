"""
Suivi des reponses des destinataires.

Principe
--------
On lit la boite de reception du compte Outlook (via Microsoft Graph, scope
Mail.Read) et on rapproche chaque message recu d'un destinataire de campagne :

  - en priorite par fil de conversation (conversationId capture a l'envoi,
    quand le suivi des reponses est actif) : association la plus fiable ;
  - a defaut par adresse email de l'expediteur (fonctionne aussi pour les
    campagnes deja envoyees, mais un message sans rapport de la meme personne
    peut compter a tort).

Les reponses automatiques (absence du bureau, accuses) sont detectees et
marquees comme telles (signal distinct d'une vraie reponse humaine).

Ce module ne fait que preparer les enregistrements ; l'association effective
en base est realisee par Database.apply_replies().
"""

import re

# En-tetes indiquant un message genere automatiquement (RFC 3834 et usages
# courants Microsoft/tiers).
_AUTO_HEADERS = {
    "auto-submitted": lambda v: v.strip().lower() not in ("", "no"),
    "x-autoreply": lambda v: True,
    "x-autorespond": lambda v: True,
    "x-auto-response-suppress": lambda v: True,
    "precedence": lambda v: v.strip().lower() in ("auto_reply", "bulk", "junk"),
}

# Motifs d'objet typiques d'une reponse automatique (FR + EN).
_AUTO_SUBJECT_RE = re.compile(
    r"(r[ée]ponse\s+automatique|absence\s+du\s+bureau|absent[e]?\s+du\s+bureau"
    r"|message\s+d['e]absence|out\s+of\s+office|automatic\s+reply|auto\s*reply"
    r"|undeliverable|non\s+remise|delivery\s+status)",
    re.IGNORECASE,
)


def sender_email(message: dict) -> str:
    """Adresse email de l'expediteur (minuscule), '' si absente."""
    try:
        addr = message.get("from", {}).get("emailAddress", {}).get("address", "")
        return (addr or "").strip().lower()
    except Exception:
        return ""


def is_auto_reply(message: dict) -> bool:
    """Detecte une reponse automatique (en-tetes puis objet)."""
    for h in (message.get("internetMessageHeaders") or []):
        name = str(h.get("name", "")).strip().lower()
        test = _AUTO_HEADERS.get(name)
        if test:
            try:
                if test(str(h.get("value", ""))):
                    return True
            except Exception:
                pass
    subject = str(message.get("subject", "") or "")
    return bool(_AUTO_SUBJECT_RE.search(subject))


def build_reply_records(messages) -> list:
    """
    Transforme des messages Graph en enregistrements pour Database.apply_replies().

    Retourne une liste de dicts :
      {message_id, email, conversation_id, received_at, auto}
    Les messages sans expediteur exploitable sont ignores.
    """
    records = []
    for m in (messages or []):
        email = sender_email(m)
        if not email:
            continue
        records.append({
            "message_id": m.get("id") or m.get("internetMessageId") or "",
            "email": email,
            "conversation_id": (m.get("conversationId") or "").strip(),
            "received_at": (m.get("receivedDateTime") or "").strip(),
            "auto": is_auto_reply(m),
        })
    return records
