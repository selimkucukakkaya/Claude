# Outlook → Telegram → Claude Asistanı

Gelen Outlook maillerini Telegram üzerinden özetleyip; arşive taşıma, detay gösterme, Claude ile cevap taslağı hazırlama ve onayla gönderme akışı sağlayan minimum iskelet.

## Akış

1. Microsoft Graph, Inbox'a gelen her yeni mail için bu servise webhook (POST) atar.
2. Servis maili çeker, Claude ile özetler, Telegram'a özet + butonlar gönderir.
3. Butonlar:
   - **Detay** – mailin tam metni
   - **Ekler** – dosyaları indirir, Telegram'a gönderir
   - **→ Arşiv** – maili belirtilen klasöre taşır
   - **Cevapla** – bir yönlendirme (örn. "toplantıyı reddet") ister, Claude taslağı hazırlar; onaylarsan Outlook üzerinden `reply` atılır.

## Ön koşullar

1. **Azure AD app registration**
   - Delegated permissions: `Mail.ReadWrite`, `Mail.Send`, `offline_access`
   - Redirect URI: `http://localhost:8000/auth/callback`
   - `client_id` ve `client_secret` al, `.env` içine yaz.
2. **Public HTTPS URL** – Graph webhook doğrulaması HTTPS ister. Geliştirme için `ngrok http 8000` veya Cloudflare Tunnel.
3. **Telegram Bot** – [@BotFather](https://t.me/BotFather) ile token al. Kendi Telegram user id'ni öğrenip `.env` içindeki `TELEGRAM_ALLOWED_USER_ID`'e yaz (başka biri bota yazarsa yok sayılır).
4. **Anthropic API key** – console.anthropic.com üzerinden.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # alanları doldur
python -m app.main
```

Ardından bir kereye mahsus:

```bash
# 1. Tarayıcıda aç, Microsoft hesabı ile giriş yap:
open http://localhost:8000/auth/login

# 2. Graph webhook aboneliği oluştur (her ~3 günde yenilenmeli):
curl -X POST https://<public-url>/admin/subscribe
```

Sonra Telegram'dan bota `/start` yaz. Artık gelen her mail için bildirim akacak.

## Dosyalar

- `app/config.py` – env okuma
- `app/state.py` – SQLite (token, mail, taslak)
- `app/graph_client.py` – MSAL auth, mail/folder/reply işlemleri, subscription
- `app/claude_client.py` – özet + cevap taslağı
- `app/telegram_bot.py` – bot, butonlar, konuşma akışı
- `app/webhook_server.py` – FastAPI, OAuth callback, Graph webhook
- `app/main.py` – bot + webhook'u aynı process'te çalıştırır

## Notlar ve sonraki adımlar

- Subscription 4230 dakika (~3 gün) sonra düşer. Production'da bir cron/scheduler ile `PATCH /subscriptions/{id}` çağırarak yenilenmeli.
- `ARCHIVE_FOLDER_NAME` Outlook'ta var olan bir klasörün görünen adı olmalı.
- Şu an çoklu kullanıcı desteği yok – tek kullanıcı (`MS_USER_ID`) için tasarlandı.
- Taslak gönderimi `reply` endpoint'i kullanıyor; CC/BCC/ek içeren cevaplar için `createReply` + `update` + `send` akışına geçirilebilir.
