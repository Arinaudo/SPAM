"""
Analyse anti-spam du contenu d'un mail (sans réseau).

analyze(html, subject, images) -> (score, issues)
  images : dict {cid: chemin_fichier} pour contrôler le poids des images.
  score  : 0..100 (système PROGRESSIF : on accumule les points gagnés)
  issues : liste de (niveau, libellé, détail) ; niveau ∈ 'ok' | 'warn' | 'bad'

Pondération (importance de chaque contrôle) :
  4 = majeur, 3 = fort, 2 = moyen, 1 = léger.
Crédit accordé selon le résultat :
  réussi (ok) = poids plein · avertissement (warn) = moitié · grave (bad) = 0
Score = 100 × (points gagnés) / (points possibles des contrôles évalués).
Ainsi un élément « majeur » raté pèse bien plus qu'un élément « léger ».
"""

import os
import re

FILE_SHARE = ["swisstransfer", "wetransfer", "grosfichiers", "smash.",
              "dropbox.com", "drive.google", "1fichier", "transfernow"]

SHORTENERS = ["bit.ly", "tinyurl.com", "goo.gl", "ow.ly", "t.co", "is.gd",
              "cutt.ly", "rebrand.ly", "buff.ly", "lnkd.in", "rb.gy"]

RISKY_TAGS = ["<script", "<form", "<iframe", "<object", "<embed"]

SPAM_WORDS = ["gratuit", "promo", "promotion", "urgent", "gagnez", "gagner",
              "gagné", "cliquez ici", "cliquez", "argent", "cash",
              "offre exceptionnelle", "offre limitée", "offre limitee",
              "felicitations", "félicitations", "sans engagement",
              "sans frais", "réduction", "reduction", "remise", "soldes",
              "cadeau", "crédit", "credit", "meilleur prix", "meilleur taux",
              "dernière chance", "derniere chance", "profitez",
              "argent facile", "free"]

SPAM_SYMBOLS = ["100%", "-50%", "-70%", "-30%"]

CAPS_WHITELIST = {"ICPE", "SEVESO", "BREEAM", "HQE", "BEFA", "ESFR", "RDC",
                  "SARL", "SAS", "DC", "NC", "MX", "DKIM", "DMARC", "SPF"}

# Poids par importance
W_MAJEUR, W_FORT, W_MOYEN, W_LEGER = 4, 3, 2, 1

# Crédit accordé selon le niveau (fraction du poids)
_CREDIT = {"ok": 1.0, "warn": 0.5, "bad": 0.0}


def _strip_tags(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _spam_terms(txt):
    low = txt.lower()
    found = {w for w in SPAM_WORDS
             if re.search(r"\b" + re.escape(w) + r"\b", low)}
    found |= {s for s in SPAM_SYMBOLS if s in low}
    return sorted(found)


def analyze(html, subject="", images=None):
    html = html or ""
    low = html.lower()
    text = _strip_tags(html)
    words = len(text.split())
    img_tags = re.findall(r"<img\b[^>]*>", html, re.I)
    imgs = len(img_tags)

    checks = []  # (niveau, libellé, détail, poids)

    def add(level, label, detail, weight):
        checks.append((level, label, detail, weight))

    # 1. Liens de partage de fichiers — FORT
    shares = sorted({s for s in FILE_SHARE if s in low})
    if shares:
        add("warn", "Liens de partage de fichiers",
            f"Détecté : {', '.join(shares)}. Mal vus des filtres.", W_FORT)
    else:
        add("ok", "Pas de lien de partage de fichiers", "", W_FORT)

    # 2. Liens http:// — MOYEN
    http_links = re.findall(r'href=["\']http://', html, re.I)
    if http_links:
        add("warn", "Liens non sécurisés (http://)",
            f"{len(http_links)} lien(s) en http:// — préférez https://.", W_MOYEN)
    else:
        add("ok", "Liens en https", "", W_MOYEN)

    # 3. Liens raccourcis — FORT
    short = sorted({s for s in SHORTENERS if s in low})
    if short:
        add("warn", "Liens raccourcis",
            f"Détecté : {', '.join(short)} — mal vus des filtres.", W_FORT)
    else:
        add("ok", "Pas de lien raccourci", "", W_FORT)

    # 4. Balises risquées — MAJEUR
    risky = [t.lstrip("<") for t in RISKY_TAGS if t in low]
    if risky:
        add("bad", "Balises risquées",
            f"Présence de <{'>, <'.join(risky)}> (souvent bloquées).", W_MAJEUR)
    else:
        add("ok", "Pas de balise risquée", "", W_MAJEUR)

    # 5. MAJUSCULES — MOYEN
    caps = [c for c in re.findall(r"\b[A-ZÀ-Þ]{4,}\b", text)
            if c not in CAPS_WHITELIST]
    if len(caps) >= 4:
        add("warn", "Beaucoup de mots en MAJUSCULES",
            "Ex. : " + ", ".join(caps[:6]), W_MOYEN)
    else:
        add("ok", "Pas d'excès de majuscules", "", W_MOYEN)

    # 6. Points d'exclamation — MOYEN
    if "!!!" in text or text.count("!") >= 5:
        add("warn", "Trop de points d'exclamation",
            "Évitez les « !!! » et l'excès de « ! ».", W_MOYEN)
    else:
        add("ok", "Ponctuation correcte", "", W_MOYEN)

    # 7. Vocabulaire commercial (corps) — FORT
    body_words = _spam_terms(text)
    if body_words:
        add("warn", "Vocabulaire commercial",
            "Détecté : " + ", ".join(body_words), W_FORT)
    else:
        add("ok", "Pas de vocabulaire trop commercial", "", W_FORT)

    # 8. Ratio texte / image — MAJEUR
    if words < 30 and imgs >= 1:
        add("bad", "Trop peu de texte",
            f"{words} mots pour {imgs} image(s) — risque « mail tout en image ».", W_MAJEUR)
    elif imgs and words / max(1, imgs) < 50:
        add("warn", "Ratio texte / image faible",
            f"{words} mots pour {imgs} image(s).", W_MAJEUR)
    else:
        add("ok", "Bon ratio texte / image",
            f"{words} mots, {imgs} image(s).", W_MAJEUR)

    # 9. Poids des images — LÉGER
    used = set(re.findall(r'src=["\']cid:([^"\']+)["\']', html, re.I))
    total = 0
    heavy = []
    for cid in used:
        p = (images or {}).get(cid)
        if p and os.path.exists(p):
            sz = os.path.getsize(p)
            total += sz
            if sz > 1_000_000:
                heavy.append(f"{cid} ({sz // 1024} Ko)")
    if heavy:
        add("warn", "Image(s) trop lourde(s)",
            ", ".join(heavy) + " — compressez sous 1 Mo.", W_LEGER)
    elif total > 2_500_000:
        add("warn", "Images totales lourdes",
            f"{total // 1024} Ko au total — allégez.", W_LEGER)
    elif used and total:
        add("ok", "Poids des images correct",
            f"{total // 1024} Ko au total.", W_LEGER)

    # 10. Nombre de liens vs texte — LÉGER
    nlinks = len(re.findall(r"<a\b[^>]*href=", html, re.I))
    if nlinks and words and nlinks > max(5, words / 40):
        add("warn", "Beaucoup de liens", f"{nlinks} liens pour {words} mots.", W_LEGER)
    elif nlinks:
        add("ok", "Nombre de liens raisonnable", f"{nlinks} lien(s).", W_LEGER)

    # 11. Images sans attribut alt — LÉGER
    no_alt = [t for t in img_tags if not re.search(r'\balt\s*=', t, re.I)]
    if no_alt:
        add("warn", "Images sans texte alternatif (alt)",
            f"{len(no_alt)} image(s) sans attribut alt.", W_LEGER)
    elif img_tags:
        add("ok", "Images avec attribut alt", "", W_LEGER)

    # 12. Désinscription — MOYEN
    if re.search(r"désinscri|desinscri|unsubscribe|désabonn|desabonn", low):
        add("ok", "Mention de désinscription présente", "", W_MOYEN)
    else:
        add("warn", "Pas de lien de désinscription",
            "Recommandé (RGPD) pour de la prospection.", W_MOYEN)

    # 13. Personnalisation — MOYEN
    if "__greeting__" in low or "__closing__" in low:
        add("ok", "Personnalisation active",
            "Salutation / politesse variables détectées.", W_MOYEN)
    else:
        add("warn", "Personnalisation non détectée",
            "Ajoutez __GREETING__ et __CLOSING__.", W_MOYEN)

    # 14. Objet
    if not subject:
        add("warn", "Objet vide", "Renseignez un objet.", W_FORT)
    else:
        if len(subject) > 70:
            add("warn", "Objet trop long",
                f"{len(subject)} caractères — visez moins de 60.", W_LEGER)
        elif len(subject) < 10:
            add("warn", "Objet très court", f"{len(subject)} caractères.", W_LEGER)
        else:
            add("ok", "Longueur d'objet correcte", f"{len(subject)} caractères.", W_LEGER)
        if subject.isupper():
            add("warn", "Objet en MAJUSCULES", subject[:70], W_MOYEN)
        if "!" in subject:
            add("warn", "Point d'exclamation dans l'objet", subject[:70], W_MOYEN)
        sub_terms = _spam_terms(subject)
        if sub_terms:
            add("warn", "Mots commerciaux dans l'objet", ", ".join(sub_terms), W_FORT)

    # --- Score progressif pondéré ---
    earned = sum(_CREDIT[lvl] * w for lvl, _, _, w in checks)
    possible = sum(w for _, _, _, w in checks)
    score = round(100 * earned / possible) if possible else 100

    issues = [(lvl, label, detail) for lvl, label, detail, _ in checks]
    return score, issues
