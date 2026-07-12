# 🕌 Arabiy — arab tilini o'rgatuvchi Telegram bot (Mini App)

To'liq reja: [PLAN.md](PLAN.md)

## Talablar

- Python 3.12+
- Node.js 20+
- Telegram bot tokeni (@BotFather)

## O'rnatish (bir marta)

```powershell
# Python bog'liqliklari
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# Frontend bog'liqliklari
cd webapp
npm install
```

`.env` faylini to'ldiring (namuna: `.env.example`):

```
BOT_TOKEN=123456:ABC...          # @BotFather'dan
WEBAPP_URL=https://...           # tunnel yoki domen (HTTPS shart!)
ANTHROPIC_API_KEY=sk-ant-...     # 3-bosqichdan boshlab kerak
```

## Ishga tushirish (dev)

**1-terminal — backend (API + bot):**

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --port 8000 --app-dir backend
```

**2-terminal — frontend (Mini App):**

```powershell
cd webapp
npm run dev          # http://localhost:5173
```

**3-terminal — HTTPS tunnel** (Telegram Mini App faqat HTTPS URLda ochiladi):

```powershell
cloudflared tunnel --url http://localhost:5173
```

Tunnel bergan `https://....trycloudflare.com` manzilini `.env` dagi
`WEBAPP_URL` ga yozing va backendni qayta ishga tushiring.
Keyin Telegramda botga `/start` yuboring — "🕌 O'rganishni boshlash"
tugmasi Mini Appni ochadi.

> Eslatma: birinchi ishga tushishda backend 30–60 soniya import qilishi
> mumkin (OneDrive/antivirus sekinlashtiradi) — kutish normal.

## Prod rejim

`cd webapp && npm run build` → FastAPI `webapp/dist` ni o'zi xizmat qiladi
(`http://localhost:8000/`), alohida Vite server kerak emas.
