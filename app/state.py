import json
import os
import aiosqlite

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mails (
    message_id TEXT PRIMARY KEY,
    telegram_message_id INTEGER,
    summary TEXT,
    subject TEXT,
    sender TEXT,
    received_at TEXT,
    status TEXT DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS drafts (
    message_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def save_token(key: str, token: dict) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO tokens(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(token)),
        )
        await db.commit()


async def load_token(key: str) -> dict | None:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute("SELECT value FROM tokens WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
    return json.loads(row[0]) if row else None


async def upsert_mail(message_id: str, subject: str, sender: str, received_at: str,
                      summary: str, telegram_message_id: int | None = None) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO mails(message_id, telegram_message_id, summary, subject, sender, received_at) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(message_id) DO UPDATE SET "
            "telegram_message_id=excluded.telegram_message_id, summary=excluded.summary",
            (message_id, telegram_message_id, summary, subject, sender, received_at),
        )
        await db.commit()


async def get_mail(message_id: str) -> dict | None:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM mails WHERE message_id = ?", (message_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def set_mail_status(message_id: str, status: str) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE mails SET status = ? WHERE message_id = ?", (status, message_id))
        await db.commit()


async def save_draft(message_id: str, body: str) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO drafts(message_id, body) VALUES(?, ?) "
            "ON CONFLICT(message_id) DO UPDATE SET body=excluded.body, "
            "updated_at=CURRENT_TIMESTAMP",
            (message_id, body),
        )
        await db.commit()


async def load_draft(message_id: str) -> str | None:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute("SELECT body FROM drafts WHERE message_id = ?", (message_id,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None
