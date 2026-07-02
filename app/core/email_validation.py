"""
Validation des adresses email avant envoi (repris de validate_emails.py).

3 niveaux :
  1. Syntaxe (regex)
  2. MX du domaine (DNS)  -> domaine capable de recevoir du mail
  3. Sonde SMTP (RCPT TO) -> l'adresse existe, sans rien envoyer

Statuts : 'VALIDE', 'INVALIDE', 'INCERTAIN'.
- VALIDE     : a envoyer
- INVALIDE   : ne PAS envoyer (sera marque non valide)
- INCERTAIN  : envoi possible (provider grand public, port 25 bloque, greylist...)

Mode MX-seul (do_smtp=False) : rapide, ne teste pas l'existence de l'adresse
(utile car le port 25 est souvent bloque par les FAI). Mode MX+SMTP : plus
precis mais plus lent et dependant du reseau.
"""

import re
import smtplib
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import dns.resolver
    HAS_DNS = True
except Exception:
    HAS_DNS = False

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

SMTP_TIMEOUT = 10
DNS_TIMEOUT = 8
SENDER_FROM = "verify@castignac.com"
HELO_DOMAIN = "castignac.com"

SMTP_OK = (250, 251)
SMTP_INVALID = (550, 551, 553, 554)
SMTP_DEFERRED = (421, 450, 451, 452)

# Providers grand public : serveurs souvent "catch-all", le probe ne sert a rien
CATCH_ALL_DOMAINS = {
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.fr", "outlook.com", "outlook.fr", "live.com",
    "live.fr", "msn.com",
    "yahoo.com", "yahoo.fr", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "pm.me",
    "aol.com", "aol.fr",
    "orange.fr", "wanadoo.fr",
    "free.fr", "freebox.fr", "freesurf.fr",
    "laposte.net",
    "sfr.fr", "neuf.fr", "9online.fr",
    "bbox.fr", "numericable.fr", "numericable.com",
    "gmx.fr", "gmx.com",
    "voila.fr", "club-internet.fr", "tele2.fr",
}

_mx_cache = {}


def syntax_ok(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email or ""))


def get_mx_hosts(domain: str):
    if not HAS_DNS:
        return None  # impossible de verifier
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)
        mx_records = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in answers])
        hosts = [host for _, host in mx_records]
    except Exception:
        hosts = []
    _mx_cache[domain] = hosts
    return hosts


def smtp_probe(email: str, mx_host: str):
    try:
        with smtplib.SMTP(mx_host, 25, timeout=SMTP_TIMEOUT) as smtp:
            smtp.helo(HELO_DOMAIN)
            smtp.mail(SENDER_FROM)
            code, message = smtp.rcpt(email)
            try:
                msg_text = message.decode("utf-8", errors="ignore")[:80]
            except Exception:
                msg_text = str(message)[:80]
            if code in SMTP_OK:
                return ("VALIDE", f"OK {code}")
            if code in SMTP_INVALID:
                return ("INVALIDE", f"{code} {msg_text}")
            if code in SMTP_DEFERRED:
                return ("INCERTAIN", f"diff {code} {msg_text}")
            return ("INCERTAIN", f"{code} {msg_text}")
    except smtplib.SMTPServerDisconnected:
        return ("INCERTAIN", "Serveur deconnecte (greylist probable)")
    except smtplib.SMTPConnectError as e:
        return ("INCERTAIN", f"Connexion refusee : {str(e)[:60]}")
    except socket.timeout:
        return ("INCERTAIN", "Timeout SMTP")
    except socket.gaierror:
        return ("INCERTAIN", "Erreur DNS sur MX")
    except OSError as e:
        if "10013" in str(e) or "Permission" in str(e):
            return ("INCERTAIN", "Port 25 bloque par le reseau/FAI")
        return ("INCERTAIN", f"OS error : {str(e)[:60]}")
    except Exception as e:
        return ("INCERTAIN", f"{type(e).__name__} : {str(e)[:60]}")


def validate_one(email: str, do_smtp: bool = True):
    """Valide une adresse. Retourne (statut, raison)."""
    email = (email or "").strip().lower()
    if not email:
        return ("INVALIDE", "Adresse vide")
    if not syntax_ok(email):
        return ("INVALIDE", "Syntaxe invalide")
    try:
        domain = email.split("@", 1)[1]
    except IndexError:
        return ("INVALIDE", "Pas de domaine")

    if not HAS_DNS:
        return ("INCERTAIN", "Verification DNS indisponible (dnspython manquant)")

    if domain in CATCH_ALL_DOMAINS:
        return ("INCERTAIN", f"Provider grand public ({domain}) — non testable")

    mx_hosts = get_mx_hosts(domain)
    if mx_hosts is None:
        return ("INCERTAIN", "DNS indisponible")
    if not mx_hosts:
        return ("INVALIDE", f"Aucun serveur MX pour {domain}")

    if not do_smtp:
        return ("VALIDE", "Domaine MX OK")

    return smtp_probe(email, mx_hosts[0])


def validate_many(emails, do_smtp=True, max_workers=8,
                  progress_cb=None, stop_cb=None):
    """
    Valide une liste d'adresses en parallele.

    progress_cb(done, total, statut, email) appele apres chaque adresse.
    stop_cb() -> True pour interrompre proprement.
    Retourne {email_lower: (statut, raison)}.
    """
    emails = [str(e or "").strip().lower() for e in emails]
    uniques = list(dict.fromkeys([e for e in emails if e]))
    total = len(uniques)
    results = {}
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(validate_one, e, do_smtp): e for e in uniques}
        for fut in as_completed(futures):
            if stop_cb and stop_cb():
                break
            email = futures[fut]
            try:
                statut, raison = fut.result()
            except Exception as e:
                statut, raison = ("INCERTAIN", str(e)[:60])
            results[email] = (statut, raison)
            done += 1
            if progress_cb:
                progress_cb(done, total, statut, email)
    return results
