from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import msal

from .config import settings
from . import state


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "offline_access",
    "Mail.ReadWrite",
    "Mail.Send",
    "MailboxSettings.Read",
]


def _msal_app() -> msal.ConfidentialClientApplication:
    authority = f"https://login.microsoftonline.com/{settings.ms_tenant_id}"
    return msal.ConfidentialClientApplication(
        settings.ms_client_id,
        client_credential=settings.ms_client_secret,
        authority=authority,
    )


def build_auth_url() -> str:
    return _msal_app().get_authorization_request_url(
        SCOPES,
        redirect_uri=settings.ms_redirect_uri,
        prompt="select_account",
    )


async def exchange_code(code: str) -> dict:
    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=settings.ms_redirect_uri,
    )
    if "access_token" not in result:
        raise RuntimeError(f"Token exchange failed: {result}")
    await state.save_token("graph", result)
    return result


async def _access_token() -> str:
    token = await state.load_token("graph")
    if not token:
        raise RuntimeError("Graph not authorized. Visit /auth/login first.")
    app = _msal_app()
    accounts = app.get_accounts()
    if accounts:
        refreshed = app.acquire_token_silent(SCOPES, account=accounts[0])
        if refreshed and "access_token" in refreshed:
            await state.save_token("graph", refreshed)
            return refreshed["access_token"]
    if "refresh_token" in token:
        refreshed = app.acquire_token_by_refresh_token(token["refresh_token"], scopes=SCOPES)
        if "access_token" in refreshed:
            await state.save_token("graph", refreshed)
            return refreshed["access_token"]
    return token["access_token"]


def _user_path() -> str:
    return "me" if settings.ms_user_id == "me" else f"users/{settings.ms_user_id}"


async def _client() -> httpx.AsyncClient:
    token = await _access_token()
    return httpx.AsyncClient(
        base_url=GRAPH_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


async def get_message(message_id: str) -> dict[str, Any]:
    async with await _client() as c:
        r = await c.get(f"/{_user_path()}/messages/{message_id}",
                        params={"$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,body,hasAttachments"})
        r.raise_for_status()
        return r.json()


async def list_attachments(message_id: str) -> list[dict]:
    async with await _client() as c:
        r = await c.get(f"/{_user_path()}/messages/{message_id}/attachments",
                        params={"$select": "id,name,contentType,size"})
        r.raise_for_status()
        return r.json().get("value", [])


async def download_attachment(message_id: str, attachment_id: str) -> tuple[str, bytes, str]:
    async with await _client() as c:
        r = await c.get(f"/{_user_path()}/messages/{message_id}/attachments/{attachment_id}")
        r.raise_for_status()
        data = r.json()
    import base64
    content = base64.b64decode(data["contentBytes"])
    return data["name"], content, data.get("contentType", "application/octet-stream")


async def find_folder_id(name: str) -> str | None:
    async with await _client() as c:
        r = await c.get(f"/{_user_path()}/mailFolders",
                        params={"$filter": f"displayName eq '{name}'", "$top": 1})
        r.raise_for_status()
        values = r.json().get("value", [])
    return values[0]["id"] if values else None


async def move_message(message_id: str, folder_name: str) -> dict:
    folder_id = await find_folder_id(folder_name)
    if not folder_id:
        raise RuntimeError(f"Folder not found: {folder_name}")
    async with await _client() as c:
        r = await c.post(f"/{_user_path()}/messages/{message_id}/move",
                         json={"destinationId": folder_id})
        r.raise_for_status()
        return r.json()


async def reply_message(message_id: str, body_html: str) -> None:
    async with await _client() as c:
        r = await c.post(
            f"/{_user_path()}/messages/{message_id}/reply",
            json={"comment": body_html},
        )
        r.raise_for_status()


async def create_subscription() -> dict:
    expires = (dt.datetime.utcnow() + dt.timedelta(minutes=4230)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    payload = {
        "changeType": "created",
        "notificationUrl": f"{settings.public_base_url}/graph/notifications",
        "resource": f"/{_user_path()}/mailFolders('inbox')/messages",
        "expirationDateTime": expires,
        "clientState": settings.graph_webhook_client_state,
    }
    async with await _client() as c:
        r = await c.post("/subscriptions", json=payload)
        r.raise_for_status()
        data = r.json()
    return data
