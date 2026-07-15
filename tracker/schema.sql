-- ============================================================
-- Schema D1 du tracker d'ouverture
-- ============================================================
-- Une ligne par CHARGEMENT du pixel (chaque ouverture du mail).
-- On agrege ensuite cote /stats (COUNT, MIN, MAX) par token.
--
-- token : identifiant unique du mail (= ref sans le prefixe "ref:")
-- ts    : date/heure UTC du chargement (ISO 8601)
-- ip    : IP du client ayant charge l'image
-- ua    : User-Agent du client
-- ============================================================

CREATE TABLE IF NOT EXISTS opens (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    ts    TEXT NOT NULL,
    ip    TEXT DEFAULT '',
    ua    TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_opens_token ON opens(token);
CREATE INDEX IF NOT EXISTS idx_opens_ts    ON opens(ts);
