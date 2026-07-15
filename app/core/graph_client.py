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
# Mail.Read : necessaire pour le suivi des reponses (lecture de la boite de
# reception). Si tu ajoutes/retires un scope, le collegue devra se reconnecter
# une fois pour accepter le nouvel acces.
SCOPE = ["Mail.Send", "Mail.Read", "User.Read"]


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

    @staticmethod
    def _build_message(to_email, subject, body_html,
                       inline_images=None, ref=None, file_attachments=None):
        """Construit le dict `message` Graph (partage envoi direct / brouillon)."""
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
        for doc in (file_attachments or []):
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": doc["name"],
                "contentType": doc.get("content_type", "application/octet-stream"),
                "contentBytes": doc["b64"],
                "isInline": False,
            })
        if attachments:
            message["attachments"] = attachments

        if ref:
            message["internetMessageHeaders"] = [
                {"name": "x-mailing-ref", "value": ref}
            ]
        return message

    def send_mail(self, token, to_email, subject, body_html,
                  inline_images=None, ref=None, save_to_sent=True,
                  file_attachments=None):
        """
        Envoie un mail HTML via Graph (endpoint /me/sendMail, un seul appel).

        inline_images    : liste de dicts {cid, name, content_type, b64}
                           (images referencees dans le HTML par <img src="cid:...">).
        file_attachments : liste de dicts {name, content_type, b64} ; pieces
                           jointes classiques (PDF, XLSX, DOCX...), non inline.
        ref              : valeur d'en-tete x-mailing-ref (variation d'empreinte).

        Leve une exception en cas d'echec (status != 202).
        """
        message = self._build_message(to_email, subject, body_html,
                                       inline_images=inline_images, ref=ref,
                                       file_attachments=file_attachments)
        payload = {"message": message, "saveToSentItems": bool(save_to_sent)}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{GRAPH_API_ENDPOINT}/me/sendMail"
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 202:
            raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:400]}")

    def create_and_send_mail(self, token, to_email, subject, body_html,
                             inline_images=None, ref=None, save_to_sent=True,
                             file_attachments=None):
        """
        Cree un brouillon PUIS l'envoie, en deux appels Graph.

        Interet : contrairement a /me/sendMail, la creation du brouillon
        renvoie l'identifiant de conversation (conversationId). On le retourne
        pour permettre le suivi des reponses par fil de conversation.

        NB : un mail envoye depuis un brouillon est toujours enregistre dans
        les Elements envoyes (le parametre save_to_sent n'a alors pas d'effet ;
        il est conserve pour l'homogeneite de la signature).

        Retourne le conversationId (str) ou "" si indisponible.
        Leve une exception en cas d'echec.
        """
        message = self._build_message(to_email, subject, body_html,
                                       inline_images=inline_images, ref=ref,
                                       file_attachments=file_attachments)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # 1) Creation du brouillon.
        r = requests.post(f"{GRAPH_API_ENDPOINT}/me/messages",
                          headers=headers, json=message, timeout=30)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {r.status_code} (brouillon) : {r.text[:400]}")
        created = r.json()
        msg_id = created.get("id")
        conversation_id = created.get("conversationId", "") or ""

        # 2) Envoi du brouillon.
        r2 = requests.post(f"{GRAPH_API_ENDPOINT}/me/messages/{msg_id}/send",
                           headers=headers, timeout=30)
        if r2.status_code not in (202, 200, 204):
            raise RuntimeError(f"HTTP {r2.status_code} (envoi) : {r2.text[:400]}")
        return conversation_id

    def list_inbox_messages(self, token, since_iso=None, page_size=50,
                            max_messages=1000):
        """
        Recupere les messages de la boite de reception (les plus recents d'abord).

        since_iso : filtre optionnel receivedDateTime >= since_iso (UTC ISO 8601).
        Gere la pagination (@odata.nextLink) et plafonne a max_messages.

        Chaque message renvoye contient : id, conversationId, receivedDateTime,
        subject, from et internetMessageHeaders (pour detecter les reponses
        automatiques).
        """
        headers = {"Authorization": f"Bearer {token}"}
        select = ("id,conversationId,receivedDateTime,subject,from,"
                  "internetMessageId,internetMessageHeaders")
        params = {
            "$select": select,
            "$orderby": "receivedDateTime desc",
            "$top": int(page_size),
        }
        if since_iso:
            params["$filter"] = f"receivedDateTime ge {since_iso}"
        url = f"{GRAPH_API_ENDPOINT}/me/mailFolders/inbox/messages"

        messages = []
        while url and len(messages) < max_messages:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:400]}")
            data = resp.json()
            messages.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None  # le nextLink contient deja tous les parametres
        return messages[:max_messages]


def file_to_b64(path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
