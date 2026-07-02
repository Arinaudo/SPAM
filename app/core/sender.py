"""
Worker d'envoi : thread Qt qui traite la file d'attente d'une campagne.

- Cadence configurable (delai aleatoire entre deux mails, defaut 5-8 s).
- Pause / Reprise / Arret a chaud (sans perdre la progression : tout est en base).
- Rafraichissement silencieux du jeton (sessions longues > 1 h).
- Emissions de signaux pour mettre l'interface a jour (progression, log, fin).
"""

import random
import time

from PySide6.QtCore import QThread, Signal

from . import personalize


class SendWorker(QThread):
    progress = Signal(dict)          # {sent, error, pending, total, last_email, last_status}
    item_done = Signal(str, str, str)  # email, status, error
    log = Signal(str)
    finished_reason = Signal(str)    # 'completed' | 'stopped' | 'auth_error'

    def __init__(self, db, graph_client, campaign_id, settings, parent=None):
        super().__init__(parent)
        self.db = db
        self.graph = graph_client
        self.campaign_id = campaign_id
        self.settings = settings
        self._stop = False
        self._paused = False

    # -- controles --------------------------------------------------------
    def request_stop(self):
        self._stop = True

    def pause(self):
        self._paused = True
        self.log.emit("Envoi mis en pause.")

    def resume(self):
        self._paused = False
        self.log.emit("Reprise de l'envoi.")

    def _interruptible_sleep(self, seconds):
        """Dort par tranches de 0,1 s en restant reactif au stop/pause."""
        end = time.time() + seconds
        while time.time() < end:
            if self._stop:
                return
            time.sleep(0.1)

    # -- boucle principale -----------------------------------------------
    def run(self):
        campaign = self.db.get_campaign(self.campaign_id)
        if not campaign:
            self.finished_reason.emit("stopped")
            return

        token = self.graph.get_token_silent()
        if not token:
            self.log.emit("Non connecte a Outlook : impossible de demarrer.")
            self.finished_reason.emit("auth_error")
            return

        import json
        cid_to_path = {}
        try:
            cid_to_path = json.loads(campaign.get("images_json") or "{}")
        except Exception:
            pass

        body_template = campaign["body_html"]
        subject = campaign["subject"]
        delay_min = float(campaign.get("delay_min", 5.0))
        delay_max = float(campaign.get("delay_max", 8.0))
        save_to_sent = bool(campaign.get("save_to_sent", 1))
        add_ref = bool(campaign.get("add_ref", 1))

        # Salutations / formules propres a la campagne
        try:
            campaign_closings = json.loads(campaign.get("closings_json") or "[]")
        except Exception:
            campaign_closings = []
        overrides = {
            "greeting_monsieur": campaign.get("greeting_monsieur", ""),
            "greeting_madame": campaign.get("greeting_madame", ""),
            "greeting_fallback": campaign.get("greeting_fallback", ""),
            "closing_salutations": campaign_closings,
            "signature_html": campaign.get("signature_html", ""),
        }

        self.db.set_campaign_status(self.campaign_id, "running")
        last_token_refresh = time.time()
        processed_since_save = 0

        while not self._stop:
            # gestion de la pause
            if self._paused:
                self.db.set_campaign_status(self.campaign_id, "paused")
                while self._paused and not self._stop:
                    time.sleep(0.2)
                if self._stop:
                    break
                self.db.set_campaign_status(self.campaign_id, "running")

            item = self.db.next_pending(self.campaign_id)
            if not item:
                self.db.set_campaign_status(self.campaign_id, "completed")
                self.finished_reason.emit("completed")
                self._emit_progress("", "")
                return

            # rafraichit le jeton toutes les ~30 min
            if time.time() - last_token_refresh > 1800:
                t = self.graph.get_token_silent()
                if t:
                    token = t
                    last_token_refresh = time.time()

            recipient = {
                "email": item["email"], "genre": item["genre"],
                "prenom": item["prenom"], "nom": item["nom"],
                "societe": item["societe"],
            }
            ref = personalize.build_invisible_ref() if add_ref else None
            html = personalize.render_body(body_template, recipient, self.settings,
                                           ref=ref, overrides=overrides)
            inline_images = personalize.collect_inline_images(html, cid_to_path)

            try:
                self.graph.send_mail(token, item["email"], subject, html,
                                     inline_images=inline_images,
                                     ref=ref if add_ref else None,
                                     save_to_sent=save_to_sent)
                self.db.mark_item(item["id"], "sent", "", ref or "")
                self.item_done.emit(item["email"], "sent", "")
                self.log.emit(f"[OK] {item['email']}")
            except Exception as e:
                msg = str(e)
                # jeton expire : on tente un rafraichissement puis un seul retry
                if "401" in msg or "InvalidAuthenticationToken" in msg:
                    t = self.graph.get_token_silent()
                    if t:
                        token = t
                        last_token_refresh = time.time()
                        try:
                            self.graph.send_mail(token, item["email"], subject, html,
                                                 inline_images=inline_images,
                                                 ref=ref if add_ref else None,
                                                 save_to_sent=save_to_sent)
                            self.db.mark_item(item["id"], "sent", "", ref or "")
                            self.item_done.emit(item["email"], "sent", "")
                            self.log.emit(f"[OK] {item['email']} (apres reconnexion)")
                            self._after_send(delay_min, delay_max)
                            continue
                        except Exception as e2:
                            msg = str(e2)
                self.db.mark_item(item["id"], "error", msg, ref or "")
                self.item_done.emit(item["email"], "error", msg)
                self.log.emit(f"[ERREUR] {item['email']} -> {msg[:120]}")

            self._emit_progress(item["email"], "sent")
            self._after_send(delay_min, delay_max)

        # arret demande
        self.db.set_campaign_status(self.campaign_id, "paused")
        self.finished_reason.emit("stopped")

    def _after_send(self, delay_min, delay_max):
        if self._stop:
            return
        self._interruptible_sleep(random.uniform(delay_min, max(delay_min, delay_max)))

    def _emit_progress(self, last_email, last_status):
        c = self.db.counts(self.campaign_id)
        c["last_email"] = last_email
        c["last_status"] = last_status
        self.progress.emit(c)
