"""
Connexion et envoi via Microsoft Graph API (Outlook / Microsoft 365).

Authentification interactive (PublicClientApplication) avec cache de jeton
persistant sur disque : le collegue ne se connecte qu'une fois, puis le jeton
est rafraichi silencieusement.

NOTE SECURITE : le flux interactif n'utilise PAS de CLIENT_SECRET. L'ancien
secret present dans envoi_emails.py etait inutile et a ete retire. Pense a le
revoquer cote Azure par precaution.
"""

import base64
from pathlib import Path

import msal
import requests

GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"
SCOPE = ["Mail.Send", "User.Read"]


class GraphAuthError(Exception):
    pass


class GraphClient:
    """Encapsule l'authentification MSAL et l'envoi de mails Graph."""

    def __init__(self, client_id: str, tenant_id: str = "common",
                 token_cache_path: Path = None):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.token_cache_path = Path(token_cache_path) if token_cache_path else None

        self._cache = msal.SerializableTokenCache()
        if self.token_cache_path and self.token_cache_path.exists():
            try:
                self._cache.deserialize(self.token_cache_path.read_text())
            except Exception:
                pass

        self._app = msal.PublicClientApplication(
            self.client_id,
            authority=self.authority,
            token_cache=self._cache,
        )

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------

    def _persist_cache(self):
        if self.token_cache_path and self._cache.has_state_changed:
            self.token_cache_path.write_text(self._cache.serialize())

    def get_token_silent(self):
        """Tente de recuperer un jeton sans interaction. None si impossible."""
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPE, account=accounts[0])
            if result and "access_token" in result:
                self._persist_cache()
                return result["access_token"]
        return None

    def get_token_interactive(self):
        """Ouvre le navigateur pour la connexion. Necessite un affichage."""
        result = self._app.acquire_token_interactive(scopes=SCOPE, prompt="select_account")
        if "access_token" not in result:
            raise GraphAuthError(result.get("error_description", "Echec de connexion"))
        self._persist_cache()
        return result["access_token"]

    def get_token(self):
        """Jeton silencieux si possible, sinon connexion interactive."""
        tok = self.get_token_silent()
        if tok:
            return tok
        return self.get_token_interactive()

    def is_logged_in(self) -> bool:
        return self.get_token_silent() is not None

    def signed_in_user(self):
        """Retourne (displayName, mail/userPrincipalName) du compte connecte."""
        tok = self.get_token_silent()
        if not tok:
            return None
        try:
            r = requests.get(
                f"{GRAPH_API_ENDPOINT}/me",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=20,
            )
            if r.status_code == 200:
                d = r.json()
                return d.get("displayName"), d.get("mail") or d.get("userPrincipalName")
        except Exception:
            pass
        return None

    def sign_out(self):
        for acc in self._app.get_accounts():
            self._app.remove_account(acc)
        self._cache = msal.SerializableTokenCache()
        self._app = msal.PublicClientApplication(
            self.client_id, authority=self.authority, token_cache=self._cache
        )
        if self.token_cache_path and self.token_cache_path.exists():
            try:
                self.token_cache_path.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Envoi
    # ------------------------------------------------------------------

    def send_mail(self, token, to_email, subject, body_html,
                  inline_images=None, ref=None, save_to_sent=True):
        """
        Envoie un mail HTML via Graph.

        inline_images : liste de dicts {cid, name, content_type, b64}
                        (images referencees dans le HTML par <img src="cid:...">).
        ref           : valeur d'en-tete x-mailing-ref (variation d'empreinte).

        Leve une exception en cas d'echec (status != 202).
        """
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        }

        attachments = []
        for img in (inline_images or []):
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": img["name"],
                "contentType": img.get("content_type", "image/png"),
                "contentBytes": img["b64"],
                "contentId": img["cid"],
                "isInline": True,
            })
        if attachments:
            message["attachments"] = attachments

        if ref:
            message["internetMessageHeaders"] = [
                {"name": "x-mailing-ref", "value": ref}
            ]

        payload = {"message": message, "saveToSentItems": bool(save_to_sent)}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{GRAPH_API_ENDPOINT}/me/sendMail"
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 202:
            raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:400]}")


def file_to_b64(path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
