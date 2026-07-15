"""
Persistance SQLite : campagnes, file d'attente (destinataires + statut) et
historique. La file est persistee pour pouvoir REPRENDRE une session longue
(30/40k envois) meme apres fermeture ou plantage de l'application.

Acces protege par un verrou : le thread d'envoi et l'interface partagent la
meme base. Mode WAL active pour de meilleures performances concurrentes.
"""

import datetime
import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    subject      TEXT NOT NULL,
    body_html    TEXT NOT NULL,
    images_json  TEXT DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'draft',
    created_at   TEXT NOT NULL,
    delay_min    REAL DEFAULT 5.0,
    delay_max    REAL DEFAULT 8.0,
    save_to_sent INTEGER DEFAULT 1,
    add_ref      INTEGER DEFAULT 1,
    attachments_json  TEXT DEFAULT '[]',
    greeting_monsieur TEXT DEFAULT '',
    greeting_madame   TEXT DEFAULT '',
    greeting_fallback TEXT DEFAULT '',
    closings_json     TEXT DEFAULT '[]',
    signature_html    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS queue_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    position    INTEGER NOT NULL,
    email       TEXT NOT NULL,
    genre       TEXT DEFAULT '',
    prenom      TEXT DEFAULT '',
    nom         TEXT DEFAULT '',
    societe     TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|sent|error|invalid|skipped
    error       TEXT DEFAULT '',
    ref         TEXT DEFAULT '',
    sent_at     TEXT DEFAULT '',
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_campaign ON queue_items(campaign_id);
CREATE INDEX IF NOT EXISTS idx_queue_status   ON queue_items(campaign_id, status);

-- Cle/valeur applicatif (ex. date du dernier controle des reponses).
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Messages de reponse deja traites (evite de recompter au rafraichissement).
CREATE TABLE IF NOT EXISTS processed_replies (
    message_id   TEXT PRIMARY KEY,
    processed_at TEXT
);
"""


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """Ajoute les colonnes manquantes aux bases creees avant cette version."""
        new_cols = {
            "greeting_monsieur": "TEXT DEFAULT ''",
            "greeting_madame": "TEXT DEFAULT ''",
            "greeting_fallback": "TEXT DEFAULT ''",
            "closings_json": "TEXT DEFAULT '[]'",
            "signature_html": "TEXT DEFAULT ''",
            "attachments_json": "TEXT DEFAULT '[]'",
        }
        existing = {r["name"] for r in
                    self._conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        for col, decl in new_cols.items():
            if col not in existing:
                self._conn.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {decl}")

        # Colonnes de suivi d'ouverture et de reponse sur la file d'attente.
        queue_cols = {
            "open_count": "INTEGER DEFAULT 0",
            "opened_at": "TEXT DEFAULT ''",
            # Suivi des reponses
            "conversation_id": "TEXT DEFAULT ''",
            "replied_at": "TEXT DEFAULT ''",
            "reply_count": "INTEGER DEFAULT 0",
            "reply_type": "TEXT DEFAULT ''",   # '' | 'human' | 'auto'
        }
        existing_q = {r["name"] for r in
                      self._conn.execute("PRAGMA table_info(queue_items)").fetchall()}
        for col, decl in queue_cols.items():
            if col not in existing_q:
                self._conn.execute(f"ALTER TABLE queue_items ADD COLUMN {col} {decl}")

        # Index d'association des reponses par fil de conversation.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_conversation "
            "ON queue_items(conversation_id)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_email ON queue_items(email)")

    def close(self):
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Campagnes
    # ------------------------------------------------------------------

    def create_campaign(self, name, subject, body_html, images: dict,
                         recipients: list, delay_min, delay_max,
                         save_to_sent=True, add_ref=True,
                         greetings: dict = None, closings: list = None,
                         signature: str = "", attachments: list = None) -> int:
        greetings = greetings or {}
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO campaigns
                   (name, subject, body_html, images_json, status, created_at,
                    delay_min, delay_max, save_to_sent, add_ref, attachments_json,
                    greeting_monsieur, greeting_madame, greeting_fallback, closings_json,
                    signature_html)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, subject, body_html, json.dumps(images or {}), "draft",
                 _now(), float(delay_min), float(delay_max),
                 int(bool(save_to_sent)), int(bool(add_ref)),
                 json.dumps(attachments or []),
                 greetings.get("greeting_monsieur", ""),
                 greetings.get("greeting_madame", ""),
                 greetings.get("greeting_fallback", ""),
                 json.dumps(closings or []),
                 signature or ""),
            )
            campaign_id = cur.lastrowid
            rows = []
            for i, r in enumerate(recipients):
                status = "pending" if r.get("valid", True) else "invalid"
                err = "" if r.get("valid", True) else "Email invalide"
                rows.append((campaign_id, i, r.get("email", ""), r.get("genre", ""),
                             r.get("prenom", ""), r.get("nom", ""), r.get("societe", ""),
                             status, err))
            self._conn.executemany(
                """INSERT INTO queue_items
                   (campaign_id, position, email, genre, prenom, nom, societe, status, error)
                   VALUES (?,?,?,?,?,?,?,?,?)""", rows)
            self._conn.commit()
            return campaign_id

    def set_campaign_status(self, campaign_id, status):
        with self._lock:
            self._conn.execute("UPDATE campaigns SET status=? WHERE id=?",
                               (status, campaign_id))
            self._conn.commit()

    def get_campaign(self, campaign_id):
        with self._lock:
            row = self._conn.execute("SELECT * FROM campaigns WHERE id=?",
                                     (campaign_id,)).fetchone()
            return dict(row) if row else None

    def list_campaigns(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM campaigns ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def delete_campaign(self, campaign_id):
        with self._lock:
            self._conn.execute("DELETE FROM queue_items WHERE campaign_id=?",
                               (campaign_id,))
            self._conn.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # File d'attente
    # ------------------------------------------------------------------

    def counts(self, campaign_id) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) c FROM queue_items WHERE campaign_id=? GROUP BY status",
                (campaign_id,)).fetchall()
            d = {"pending": 0, "sent": 0, "error": 0, "invalid": 0, "skipped": 0}
            for r in rows:
                d[r["status"]] = r["c"]
            d["total"] = sum(d.values())
            return d

    def next_pending(self, campaign_id):
        """Prochain destinataire a traiter (statut pending, ordre position)."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM queue_items
                   WHERE campaign_id=? AND status='pending'
                   ORDER BY position ASC LIMIT 1""", (campaign_id,)).fetchone()
            return dict(row) if row else None

    def mark_item(self, item_id, status, error="", ref="", sent_at=None):
        with self._lock:
            self._conn.execute(
                "UPDATE queue_items SET status=?, error=?, ref=?, sent_at=? WHERE id=?",
                (status, error[:500], ref, sent_at or _now(), item_id))
            self._conn.commit()

    def reset_errors_to_pending(self, campaign_id):
        """Remet les envois en erreur a 'pending' pour re-tenter."""
        with self._lock:
            self._conn.execute(
                "UPDATE queue_items SET status='pending', error='' "
                "WHERE campaign_id=? AND status='error'", (campaign_id,))
            self._conn.commit()

    def set_conversation_id(self, item_id, conversation_id):
        """Enregistre l'identifiant de conversation d'un mail envoye (suivi reponses)."""
        if not conversation_id:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE queue_items SET conversation_id=? WHERE id=?",
                (conversation_id, item_id))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Parametres persistes (cle/valeur)
    # ------------------------------------------------------------------

    def get_meta(self, key, default=None):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_meta(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Suivi d'ouverture (pixel de tracking)
    # ------------------------------------------------------------------

    def apply_opens(self, records) -> int:
        """Met a jour open_count / opened_at des destinataires depuis les stats.

        `records` : liste de dicts {token, first_open, last_open, count} tels
        que renvoyes par le Worker (endpoint /stats). Le token est le ref sans
        le prefixe "ref:" ; on retrouve la ligne via queue_items.ref = 'ref:'||token.

        Retourne le nombre de lignes (destinataires) mises a jour.
        """
        updated = 0
        with self._lock:
            for rec in (records or []):
                token = str(rec.get("token", "")).strip()
                if not token:
                    continue
                ref = f"ref:{token}"
                count = int(rec.get("count", 0) or 0)
                opened_at = rec.get("first_open", "") or ""
                cur = self._conn.execute(
                    "UPDATE queue_items SET open_count=?, opened_at=? WHERE ref=?",
                    (count, opened_at, ref))
                updated += cur.rowcount
            self._conn.commit()
        return updated

    def open_counts(self, campaign_id) -> dict:
        """Retourne {opened, sent} pour une campagne (opened = ouvert au moins une fois)."""
        with self._lock:
            sent = self._conn.execute(
                "SELECT COUNT(*) c FROM queue_items WHERE campaign_id=? AND status='sent'",
                (campaign_id,)).fetchone()["c"]
            opened = self._conn.execute(
                "SELECT COUNT(*) c FROM queue_items "
                "WHERE campaign_id=? AND status='sent' AND open_count > 0",
                (campaign_id,)).fetchone()["c"]
            return {"opened": opened, "sent": sent}

    # ------------------------------------------------------------------
    # Suivi des reponses
    # ------------------------------------------------------------------

    def apply_replies(self, records) -> dict:
        """Associe des messages recus aux destinataires et met a jour la base.

        `records` : liste de dicts {message_id, email, conversation_id,
        received_at, auto} tels que produits par replies.build_reply_records().

        Association : d'abord par conversation_id (fil de conversation, fiable),
        sinon par adresse email (parmi les mails 'sent'). Idempotent : chaque
        message_id n'est traite qu'une fois (table processed_replies).

        Retourne {processed, matched, human, auto} (compteurs de messages).
        """
        processed = matched = human = auto = 0
        with self._lock:
            for rec in (records or []):
                mid = str(rec.get("message_id", "")).strip()
                if not mid:
                    continue
                # Deja traite ? (evite de recompter au rafraichissement)
                seen = self._conn.execute(
                    "SELECT 1 FROM processed_replies WHERE message_id=?",
                    (mid,)).fetchone()
                if seen:
                    continue

                conv = str(rec.get("conversation_id", "")).strip()
                email = str(rec.get("email", "")).strip().lower()
                received_at = str(rec.get("received_at", "")).strip()
                is_auto = bool(rec.get("auto"))

                rows = []
                if conv:
                    rows = self._conn.execute(
                        "SELECT id, reply_type, replied_at FROM queue_items "
                        "WHERE conversation_id=? AND status='sent'",
                        (conv,)).fetchall()
                if not rows and email:
                    rows = self._conn.execute(
                        "SELECT id, reply_type, replied_at FROM queue_items "
                        "WHERE lower(email)=? AND status='sent'",
                        (email,)).fetchall()

                if rows:
                    for r in rows:
                        cur_type = r["reply_type"] or ""
                        new_type = "human" if (not is_auto or cur_type == "human") \
                            else "auto"
                        new_replied_at = r["replied_at"] or received_at
                        self._conn.execute(
                            "UPDATE queue_items SET reply_count=reply_count+1, "
                            "reply_type=?, replied_at=? WHERE id=?",
                            (new_type, new_replied_at, r["id"]))
                    matched += 1
                    if is_auto:
                        auto += 1
                    else:
                        human += 1

                # Message marque comme traite (associe ou non).
                self._conn.execute(
                    "INSERT OR IGNORE INTO processed_replies(message_id, processed_at) "
                    "VALUES(?, ?)", (mid, _now()))
                processed += 1
            self._conn.commit()
        return {"processed": processed, "matched": matched,
                "human": human, "auto": auto}

    def reply_counts(self, campaign_id) -> dict:
        """Retourne {sent, replied_human, replied_auto} pour une campagne."""
        with self._lock:
            sent = self._conn.execute(
                "SELECT COUNT(*) c FROM queue_items WHERE campaign_id=? AND status='sent'",
                (campaign_id,)).fetchone()["c"]
            human = self._conn.execute(
                "SELECT COUNT(*) c FROM queue_items WHERE campaign_id=? "
                "AND status='sent' AND reply_type='human'",
                (campaign_id,)).fetchone()["c"]
            autos = self._conn.execute(
                "SELECT COUNT(*) c FROM queue_items WHERE campaign_id=? "
                "AND status='sent' AND reply_type='auto'",
                (campaign_id,)).fetchone()["c"]
            return {"sent": sent, "replied_human": human, "replied_auto": autos}

    def earliest_sent_at(self):
        """Date du plus ancien mail envoye (pour borner le scan de la boite)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(sent_at) m FROM queue_items "
                "WHERE status='sent' AND sent_at<>''").fetchone()
            return row["m"] if row and row["m"] else ""

    def items(self, campaign_id, status=None, limit=None, offset=0):
        with self._lock:
            q = "SELECT * FROM queue_items WHERE campaign_id=?"
            params = [campaign_id]
            if status:
                q += " AND status=?"
                params.append(status)
            q += " ORDER BY position ASC"
            if limit is not None:
                q += " LIMIT ? OFFSET ?"
                params += [limit, offset]
            rows = self._conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Historique (tous les envois traites, toutes campagnes)
    # ------------------------------------------------------------------

    def history(self, search="", status_filter="", limit=1000):
        with self._lock:
            q = """SELECT q.email, q.prenom, q.nom, q.societe, q.status, q.error,
                          q.sent_at, q.open_count, q.opened_at,
                          q.reply_count, q.reply_type, q.replied_at,
                          c.name AS campaign, c.subject
                   FROM queue_items q JOIN campaigns c ON c.id = q.campaign_id
                   WHERE q.status IN ('sent','error')"""
            params = []
            if status_filter in ("sent", "error"):
                q += " AND q.status=?"
                params.append(status_filter)
            if search:
                q += " AND (q.email LIKE ? OR q.nom LIKE ? OR q.societe LIKE ? OR c.subject LIKE ?)"
                like = f"%{search}%"
                params += [like, like, like, like]
            q += " ORDER BY q.sent_at DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]
