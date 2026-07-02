"""
Diagnostic d'authentification d'un domaine d'envoi : SPF, DKIM, DMARC (via DNS).

Ne modifie rien : c'est un contrôle en lecture. Activer DKIM/DMARC reste une
action côté DNS (OVH) + administration Microsoft 365.

check_all(domain) -> liste de (nom, statut, detail)
  statut ∈ 'ok' | 'warn' | 'missing' | 'error'
"""

import re

try:
    import dns.resolver
    HAS_DNS = True
except Exception:
    HAS_DNS = False

DNS_TIMEOUT = 8


def _txt_records(name):
    out = []
    try:
        for r in dns.resolver.resolve(name, "TXT", lifetime=DNS_TIMEOUT):
            try:
                out.append(b"".join(r.strings).decode("utf-8", "ignore"))
            except Exception:
                out.append(str(r).strip('"'))
    except Exception:
        pass
    return out


def _has_cname(name):
    try:
        ans = dns.resolver.resolve(name, "CNAME", lifetime=DNS_TIMEOUT)
        return str(list(ans)[0].target).rstrip(".")
    except Exception:
        return None


def check_spf(domain):
    recs = _txt_records(domain)
    spf = [r for r in recs if r.lower().startswith("v=spf1")]
    if spf:
        return ("ok", spf[0][:220])
    return ("missing", "Aucun enregistrement SPF (v=spf1) trouvé.")


def check_dmarc(domain):
    recs = _txt_records("_dmarc." + domain)
    dm = [r for r in recs if r.lower().startswith("v=dmarc1")]
    if not dm:
        return ("missing", "Aucun enregistrement DMARC trouvé sur _dmarc." + domain)
    rec = dm[0]
    m = re.search(r"\bp=([a-zA-Z]+)", rec)
    pol = m.group(1).lower() if m else "?"
    if pol == "none":
        return ("warn", f"DMARC présent mais en observation (p=none). {rec[:160]}")
    return ("ok", f"DMARC actif (p={pol}). {rec[:160]}")


def check_dkim(domain):
    # Microsoft 365 : selector1/selector2._domainkey.<domain> (CNAME), sinon TXT
    found = []
    for sel in ("selector1", "selector2"):
        host = f"{sel}._domainkey.{domain}"
        if _has_cname(host) or _txt_records(host):
            found.append(sel)
    if found:
        return ("ok", f"DKIM configuré ({', '.join(found)}).")
    return ("missing",
            "Aucun sélecteur DKIM Microsoft 365 (selector1/selector2) trouvé.")


def check_all(domain):
    domain = (domain or "").strip().lower().lstrip("@")
    if not HAS_DNS:
        return [("DNS", "error", "Module dnspython indisponible.")]
    if not domain or "." not in domain:
        return [("Domaine", "error", "Domaine invalide.")]
    return [
        ("SPF", *check_spf(domain)),
        ("DKIM", *check_dkim(domain)),
        ("DMARC", *check_dmarc(domain)),
    ]
