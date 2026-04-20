from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

from . import graph_client, state, telegram_bot
from .config import settings


log = logging.getLogger(__name__)


def build_app(tg_app) -> FastAPI:
    api = FastAPI()

    @api.get("/auth/login")
    async def auth_login():
        return RedirectResponse(graph_client.build_auth_url())

    @api.get("/auth/callback")
    async def auth_callback(code: str):
        await graph_client.exchange_code(code)
        return PlainTextResponse("OK. Artık /admin/subscribe çağırabilirsin.")

    @api.post("/admin/subscribe")
    async def admin_subscribe():
        sub = await graph_client.create_subscription()
        return {"id": sub["id"], "expires": sub["expirationDateTime"]}

    @api.post("/graph/notifications")
    async def graph_notifications(request: Request):
        # Graph validation handshake
        token = request.query_params.get("validationToken")
        if token:
            return PlainTextResponse(token, media_type="text/plain")

        payload = await request.json()
        for item in payload.get("value", []):
            if item.get("clientState") != settings.graph_webhook_client_state:
                log.warning("Bad clientState, ignoring notification")
                continue
            resource = item.get("resource", "")
            # resource örn: users/{id}/messages/{message-id}
            message_id = resource.split("/")[-1]
            try:
                await telegram_bot.notify_new_mail(tg_app, message_id)
            except Exception:
                log.exception("notify_new_mail failed for %s", message_id)
        return Response(status_code=202)

    return api
