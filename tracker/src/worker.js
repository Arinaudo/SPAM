/**
 * ============================================================
 * Worker Cloudflare - Tracker d'ouverture (pixel invisible)
 * ============================================================
 *
 * Deux routes :
 *
 *   GET /o/<token>
 *       Renvoie un GIF 1x1 transparent et enregistre l'ouverture
 *       (token, date UTC, IP, User-Agent) dans la base D1.
 *       Reponse jamais mise en cache (Cache-Control: no-store) pour
 *       compter chaque ouverture reelle.
 *
 *   GET /stats?key=<STATS_KEY>&since=<ISO facultatif>
 *       Renvoie un JSON agrege par token :
 *       { "opens": [ {token, first_open, last_open, count}, ... ] }
 *       Protege par la cle STATS_KEY (variable/secret Cloudflare).
 *
 * Le "token" est l'identifiant unique du mail : c'est le "ref" anti-spam
 * genere par l'application, sans le prefixe "ref:".
 * ============================================================
 */

// GIF transparent 1x1 (43 octets), encode en base64.
const PIXEL_B64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

function pixelResponse() {
  const bytes = Uint8Array.from(atob(PIXEL_B64), (c) => c.charCodeAt(0));
  return new Response(bytes, {
    status: 200,
    headers: {
      "Content-Type": "image/gif",
      "Content-Length": String(bytes.length),
      // Empeche toute mise en cache (client, proxy, Cloudflare) pour
      // compter chaque ouverture.
      "Cache-Control": "no-store, no-cache, must-revalidate, private, max-age=0",
      "Pragma": "no-cache",
      "Expires": "0",
    },
  });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // ---- Route pixel : /o/<token> --------------------------------------
    if (path.startsWith("/o/")) {
      let token = decodeURIComponent(path.slice(3)).trim();
      // On retire une eventuelle extension (.png / .gif) ajoutee pour faire
      // "vraie image" aux yeux de certains clients mail.
      token = token.replace(/\.(png|gif|jpg|jpeg)$/i, "");

      if (token) {
        const ts = new Date().toISOString();
        const ip = request.headers.get("CF-Connecting-IP") || "";
        const ua = request.headers.get("User-Agent") || "";
        // On enregistre sans bloquer la reponse image.
        try {
          await env.DB.prepare(
            "INSERT INTO opens (token, ts, ip, ua) VALUES (?, ?, ?, ?)"
          )
            .bind(token, ts, ip, ua)
            .run();
        } catch (e) {
          // On ne casse jamais l'affichage du pixel a cause d'une erreur DB.
        }
      }
      return pixelResponse();
    }

    // ---- Route stats : /stats -----------------------------------------
    if (path === "/stats") {
      const key = url.searchParams.get("key") || "";
      const expected = env.STATS_KEY || "";
      if (!expected || key !== expected) {
        return json({ error: "unauthorized" }, 401);
      }

      const since = url.searchParams.get("since") || "";
      let sql =
        "SELECT token, COUNT(*) AS count, MIN(ts) AS first_open, MAX(ts) AS last_open " +
        "FROM opens";
      const binds = [];
      if (since) {
        sql += " WHERE ts >= ?";
        binds.push(since);
      }
      sql += " GROUP BY token ORDER BY last_open DESC";

      try {
        const stmt = binds.length
          ? env.DB.prepare(sql).bind(...binds)
          : env.DB.prepare(sql);
        const { results } = await stmt.all();
        return json({ opens: results || [] });
      } catch (e) {
        return json({ error: String(e) }, 500);
      }
    }

    // ---- Sante ---------------------------------------------------------
    if (path === "/" || path === "/health") {
      return json({ ok: true, service: "castignac-tracker" });
    }

    return json({ error: "not found" }, 404);
  },
};
