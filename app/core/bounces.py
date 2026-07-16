"""
Detection des rapports de non-remise (NDR / bounces) dans la boite Outlook.

On lit la boite de reception (via Microsoft Graph, comme le suivi des reponses),
on repere les messages de non-remise, on en extrait les adresses en echec, et on
ne garde que celles qui figurent parmi les adresses reellement envoyees (pour
eviter les faux positifs). Ces adresses sont ensuite ajoutees a la liste de
suppression et marquees 'invalid' par Database.apply_bounces().

Ce module ne fait que preparer les enregistrements ; l'ecriture en base est
realisee par Database.apply_bounces().
"""

import re

# Adresse email (permissive mais suffisante pour extraire d'un texte).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Objets typiques d'un rapport de non-remise (FR + EN).
_NDR_SUBJECT_RE = re.compile(
    r"(undeliverable|non\s*remis|non\s*d[ée]livr|delivery\s+(has\s+)?failed"
    r"|mail\s+delivery\s+failed|delivery\s+status\s+notification"
    r"|[ée]chec\s+de\s+la\s+remise|returned\s+mail|failure\s+notice"
    r"|mail\s+delivery\s+subsystem)",
    re.IGNORECASE,
)

# Fragments d'expediteur typiques d'un serveur de messagerie.
_NDR_SENDER_FRAGMENTS = ("postmaster", "mailer-daemon", "microsoftexchange")
_NDR_NAME_FRAGMENTS = ("mail delivery", "microsoft outlook", "postmaster",
                       "mailer-daemon", "mail delivery subsystem")


def _sender_email(message: dict) -> str:
    try:
        return (message.get("from", {}).get("emailAddress", {})
                .get("address", "") or "").strip().lower()
    except Exception:
        return ""


def _sender_name(message: dict) -> str:
    try:
        return (message.get("from", {}).get("emailAddress", {})
                .get("name", "") or "").strip().lower()
    except Exception:
        return ""


def is_ndr(message: dict) -> bool:
    """Detecte un rapport de non-remise (expediteur, objet, ou en-tete report)."""
    frm = _sender_email(message)
    if any(f in frm for f in _NDR_SENDER_FRAGMENTS):
        return True
    name = _sender_name(message)
    if any(f in name for f in _NDR_NAME_FRAGMENTS):
        return True
    subject = str(message.get("subject", "") or "")
    if _NDR_SUBJECT_RE.search(subject):
        return True
    for h in (message.get("internetMessageHeaders") or []):
        if str(h.get("name", "")).lower() == "content-type":
            if "report-type=delivery-status" in str(h.get("value", "")).lower():
                return True
    return False


def _extract_emails(text: str) -> set:
    return {m.group(0).lower() for m in _EMAIL_RE.finditer(text or "")}


def build_bounce_records(messages, sent_emails) -> list:
    """
    Transforme des messages Graph en enregistrements pour Database.apply_bounces().

    `sent_emails` : ensemble des adresses reellement envoyees (minuscules).
    On n'ajoute a la suppression QUE les adresses en echec qui font partie de
    cet ensemble, pour eviter de supprimer une adresse sans rapport (postmaster,
    votre propre adresse, etc.).

    Retourne une liste de dicts {message_id, emails, reason}.
    """
    sent = {(e or "").strip().lower() for e in (sent_emails or set())}
    records = []
    for m in (messages or []):
        if not is_ndr(m):
            continue
        text = (str(m.get("subject", "") or "") + " "
                + str(m.get("bodyPreview", "") or ""))
        failed = sorted(_extract_emails(text) & sent)
        if not failed:
            continue
        subject = str(m.get("subject", "") or "").strip()
        records.append({
            "message_id": m.get("id") or m.get("internetMessageId") or "",
            "emails": failed,
            "reason": ("Non remis : " + subject)[:200] if subject else "Non remis (NDR)",
        })
    return records
