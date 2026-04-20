from anthropic import AsyncAnthropic

from .config import settings


_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


SUMMARY_PROMPT = """Aşağıdaki e-postayı Türkçe olarak özetle.
- 2-3 cümle
- Kimden, konu, ana istek/aksiyon
- Aciliyet varsa belirt
- Ekler varsa listele

Gönderen: {sender}
Konu: {subject}
Ekler: {attachments}

Mail içeriği:
---
{body}
---

Sadece özeti döndür, giriş cümlesi yazma."""


REPLY_PROMPT = """Aşağıdaki e-postaya profesyonel bir cevap taslağı hazırla.
Kullanıcının yönlendirmesi: {instruction}

Orijinal mail:
Gönderen: {sender}
Konu: {subject}
İçerik:
---
{body}
---

Türkçe, kibar ve net bir cevap yaz. Sadece cevap metnini döndür, açıklama ekleme."""


async def summarize_mail(sender: str, subject: str, body: str, attachments: list[str]) -> str:
    msg = await _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": SUMMARY_PROMPT.format(
                sender=sender,
                subject=subject,
                attachments=", ".join(attachments) if attachments else "yok",
                body=body[:8000],
            ),
        }],
    )
    return msg.content[0].text.strip()


async def draft_reply(sender: str, subject: str, body: str, instruction: str) -> str:
    msg = await _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": REPLY_PROMPT.format(
                sender=sender,
                subject=subject,
                body=body[:8000],
                instruction=instruction,
            ),
        }],
    )
    return msg.content[0].text.strip()
