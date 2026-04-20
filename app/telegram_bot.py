from __future__ import annotations

import io
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import claude_client, graph_client, state
from .config import settings


log = logging.getLogger(__name__)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _kb_new_mail(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Detay", callback_data=f"detail:{message_id}"),
            InlineKeyboardButton("Ekler", callback_data=f"att:{message_id}"),
        ],
        [
            InlineKeyboardButton("Cevapla", callback_data=f"reply:{message_id}"),
            InlineKeyboardButton(f"→ {settings.archive_folder_name}", callback_data=f"move:{message_id}"),
        ],
    ])


def _kb_draft(message_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Gönder", callback_data=f"send:{message_id}"),
            InlineKeyboardButton("Düzenle", callback_data=f"edit:{message_id}"),
        ],
        [InlineKeyboardButton("İptal", callback_data=f"cancel:{message_id}")],
    ])


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == settings.telegram_allowed_user_id


async def notify_new_mail(app: Application, message_id: str) -> None:
    msg = await graph_client.get_message(message_id)
    sender = (msg.get("from", {}) or {}).get("emailAddress", {}).get("address", "?")
    subject = msg.get("subject") or "(konusuz)"
    body = _html_to_text((msg.get("body") or {}).get("content", "") or msg.get("bodyPreview", ""))
    attachments = await graph_client.list_attachments(message_id) if msg.get("hasAttachments") else []
    att_names = [a["name"] for a in attachments]

    summary = await claude_client.summarize_mail(sender, subject, body, att_names)
    text = f"<b>{subject}</b>\n<i>{sender}</i>\n\n{summary}"
    if att_names:
        text += "\n\n📎 " + ", ".join(att_names)

    sent = await app.bot.send_message(
        chat_id=settings.telegram_allowed_user_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=_kb_new_mail(message_id),
    )
    await state.upsert_mail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        received_at=msg.get("receivedDateTime", ""),
        summary=summary,
        telegram_message_id=sent.message_id,
    )


async def _cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "Outlook otomasyonu aktif. Yeni mail geldiğinde özet + aksiyon butonları göndereceğim."
    )


async def _on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    query = update.callback_query
    await query.answer()
    action, _, message_id = query.data.partition(":")

    if action == "detail":
        msg = await graph_client.get_message(message_id)
        body = _html_to_text((msg.get("body") or {}).get("content", ""))
        chunks = [body[i:i + 3500] for i in range(0, len(body), 3500)] or ["(boş içerik)"]
        for chunk in chunks:
            await ctx.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif action == "att":
        for att in await graph_client.list_attachments(message_id):
            if att.get("size", 0) > 45 * 1024 * 1024:
                await ctx.bot.send_message(chat_id=query.message.chat_id,
                                           text=f"{att['name']} çok büyük, atlandı.")
                continue
            name, content, _ = await graph_client.download_attachment(message_id, att["id"])
            await ctx.bot.send_document(chat_id=query.message.chat_id,
                                        document=io.BytesIO(content), filename=name)

    elif action == "move":
        await graph_client.move_message(message_id, settings.archive_folder_name)
        await state.set_mail_status(message_id, "moved")
        await query.edit_message_reply_markup(reply_markup=None)
        await ctx.bot.send_message(chat_id=query.message.chat_id,
                                   text=f"✓ {settings.archive_folder_name} klasörüne taşındı.")

    elif action == "reply":
        ctx.user_data["awaiting_instruction_for"] = message_id
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text="Nasıl cevap vermek istediğini kısaca yaz (ör. 'toplantıyı kabul et, salıyı öner').",
        )

    elif action == "edit":
        ctx.user_data["awaiting_edit_for"] = message_id
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text="Nasıl değiştireyim? (ör. 'daha kısa yap', 'resmi ton kullan')",
        )

    elif action == "send":
        draft = await state.load_draft(message_id)
        if not draft:
            await ctx.bot.send_message(chat_id=query.message.chat_id, text="Taslak bulunamadı.")
            return
        html = draft.replace("\n", "<br>")
        await graph_client.reply_message(message_id, html)
        await state.set_mail_status(message_id, "replied")
        await query.edit_message_reply_markup(reply_markup=None)
        await ctx.bot.send_message(chat_id=query.message.chat_id, text="✓ Cevap gönderildi.")

    elif action == "cancel":
        await query.edit_message_reply_markup(reply_markup=None)
        await ctx.bot.send_message(chat_id=query.message.chat_id, text="Taslak iptal edildi.")


async def _on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    text = update.message.text or ""

    mid = ctx.user_data.pop("awaiting_instruction_for", None)
    if mid:
        msg = await graph_client.get_message(mid)
        body = _html_to_text((msg.get("body") or {}).get("content", ""))
        sender = (msg.get("from", {}) or {}).get("emailAddress", {}).get("address", "?")
        subject = msg.get("subject") or ""
        draft = await claude_client.draft_reply(sender, subject, body, text)
        await state.save_draft(mid, draft)
        await update.message.reply_text(
            f"<b>Taslak:</b>\n\n{draft}",
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_draft(mid),
        )
        return

    mid = ctx.user_data.pop("awaiting_edit_for", None)
    if mid:
        current = await state.load_draft(mid) or ""
        msg = await graph_client.get_message(mid)
        body = _html_to_text((msg.get("body") or {}).get("content", ""))
        sender = (msg.get("from", {}) or {}).get("emailAddress", {}).get("address", "?")
        subject = msg.get("subject") or ""
        instruction = f"Mevcut taslağı şu yönde revize et: {text}\n\nMevcut taslak:\n{current}"
        draft = await claude_client.draft_reply(sender, subject, body, instruction)
        await state.save_draft(mid, draft)
        await update.message.reply_text(
            f"<b>Güncel taslak:</b>\n\n{draft}",
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_draft(mid),
        )


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    return app
