"""
Chargement et preparation des listes de destinataires (Excel .xlsx/.xls ou CSV).

- Detection automatique des colonnes usuelles (EMAIL, GENRE, PRENOM, NOM...).
- Mapping personnalisable colonne fichier -> champ logique.
- Validation syntaxique des adresses, suppression des doublons.
"""

import re

import pandas as pd

# Champs logiques utilises par l'application
FIELDS = ["email", "genre", "prenom", "nom", "societe"]

# Mots-cles pour la detection automatique des colonnes (insensible casse/accents)
AUTODETECT = {
    "email": ["email", "e-mail", "mail", "courriel", "adresse"],
    "genre": ["genre", "civilite", "civilité", "titre", "sexe"],
    "prenom": ["prenom", "prénom", "firstname", "first name"],
    "nom": ["nom", "lastname", "last name", "name", "nom complet"],
    "societe": ["societe", "société", "company", "entreprise", "raison sociale"],
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c")):
        s = s.replace(a, b)
    return s


def read_table(path: str) -> pd.DataFrame:
    """Lit un fichier Excel ou CSV en DataFrame (tout en texte)."""
    path_l = str(path).lower()
    if path_l.endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(path, dtype=str)
    else:
        # CSV : on tente plusieurs separateurs / encodages courants
        try:
            df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(path, dtype=str, sep=";", encoding="latin-1")
    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def auto_map_columns(columns) -> dict:
    """Propose un mapping {champ_logique: nom_colonne_fichier} par detection."""
    mapping = {}
    norm_cols = {col: _norm(col) for col in columns}
    for field, keywords in AUTODETECT.items():
        for col, ncol in norm_cols.items():
            if col in mapping.values():
                continue
            if any(kw in ncol for kw in keywords):
                mapping[field] = col
                break
    return mapping


def clean_value(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def is_valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match(str(addr).strip()))


def build_recipients(df: pd.DataFrame, mapping: dict, dedupe: bool = True):
    """
    Transforme le DataFrame en liste de destinataires normalises.

    Retourne (recipients, stats) avec
      recipients : liste de dicts {email, genre, prenom, nom, societe, valid}
      stats      : {'total', 'valid', 'invalid', 'duplicates'}
    """
    recipients = []
    seen = set()
    stats = {"total": 0, "valid": 0, "invalid": 0, "duplicates": 0}

    email_col = mapping.get("email")
    if not email_col or email_col not in df.columns:
        raise ValueError("Aucune colonne EMAIL n'a ete associee.")

    for _, row in df.iterrows():
        email = clean_value(row.get(email_col, "")).lower()
        if not email:
            continue
        stats["total"] += 1

        rec = {"email": email}
        for field in ("genre", "prenom", "nom", "societe"):
            col = mapping.get(field)
            rec[field] = clean_value(row.get(col, "")) if col and col in df.columns else ""

        if not is_valid_email(email):
            rec["valid"] = False
            stats["invalid"] += 1
            recipients.append(rec)
            continue

        if dedupe and email in seen:
            stats["duplicates"] += 1
            continue
        seen.add(email)

        rec["valid"] = True
        stats["valid"] += 1
        recipients.append(rec)

    return recipients, stats
