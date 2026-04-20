from __future__ import annotations

import asyncio
import logging

import uvicorn

from . import state, telegram_bot, webhook_server


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def run() -> None:
    await state.init_db()

    tg_app = telegram_bot.build_application()
    api = webhook_server.build_app(tg_app)

    config = uvicorn.Config(api, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling()
        try:
            await server.serve()
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
