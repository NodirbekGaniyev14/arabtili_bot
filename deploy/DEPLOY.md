# 🚀 Arabiy botni DigitalOcean serverga deploy qilish

Server: `134.122.69.214` (Ubuntu 24.04) · nginx allaqachon ishlaydi (digitalcfo sayti bilan yonma-yon, tegilmaydi).

> `BOT_DOMAIN` ni haqiqiy subdomeningizga almashtiring (masalan `bot.example.com`).

---

## 0. DNS (bir marta)

Domen boshqaruv panelingizda `BOT_DOMAIN` uchun **A-yozuvi** qo'shing:

```
A    BOT_DOMAIN    →    134.122.69.214
```

Tarqalguncha 5–30 daqiqa kutilishi mumkin. Tekshirish: `ping BOT_DOMAIN` IP'ni ko'rsatsa tayyor.

---

## 1. Kodni serverga yuborish (kompyuteringizdan)

Loyiha papkangizda (Git Bash yoki PowerShell) tayyor arxivni serverga nusxalang — parol so'ralganda **server parolingizni yozasiz**:

```bash
scp arabiy-deploy.tar.gz root@134.122.69.214:/root/
```

---

## 2. Serverda o'rnatish (SSH bilan kirib)

```bash
ssh root@134.122.69.214

# Kodni /opt/arabiy ga chiqarish
mkdir -p /opt/arabiy
tar -xzf /root/arabiy-deploy.tar.gz -C /opt/arabiy

# O'rnatish skripti (venv, node, build, systemd)
cd /opt/arabiy
bash deploy/setup.sh
```

Skript tugagach backend `127.0.0.1:8000` da ishlaydi. Tekshirish:

```bash
curl http://127.0.0.1:8000/api/health      # {"status":"ok",...} bo'lishi kerak
```

---

## 3. nginx server blokini ulash

```bash
# Subdomen nomini qo'yib nginx konfigini o'rnatamiz
sed "s/BOT_DOMAIN/BOT_DOMAIN/g" /opt/arabiy/deploy/nginx-arabiy.conf \
  > /etc/nginx/sites-available/arabiy
ln -sf /etc/nginx/sites-available/arabiy /etc/nginx/sites-enabled/arabiy

nginx -t          # sintaksis tekshiruvi — "ok" bo'lishi kerak
systemctl reload nginx
```

---

## 4. HTTPS sertifikat (Let's Encrypt)

```bash
certbot --nginx -d BOT_DOMAIN --non-interactive --agree-tos -m sizning@email.uz --redirect
```

Certbot avtomatik sertifikat oladi, nginx'ga 443 blokini qo'shadi va 80→443 yo'naltiradi. Sertifikat 90 kunda avtomatik yangilanadi.

Tekshirish: brauzerda `https://BOT_DOMAIN` ochilsa (yashil qulf) — tayyor.

---

## 5. Yakuniy sozlash

- `.env` allaqachon to'g'ri (arxivda): `WEBAPP_URL=https://BOT_DOMAIN`, `DEV_AUTH=0`.
- Telegramda **@JamalArabiy_bot** ga `/start` yuboring → "O'rganishni boshlash" tugmasi endi doimiy manzilni ochadi.
- (Ixtiyoriy) @BotFather → `/setmenubutton` orqali Mini App'ni menyu tugmasi qilib qo'yish mumkin.

---

## Foydali buyruqlar

```bash
systemctl status arabiy       # holat
systemctl restart arabiy      # qayta ishga tushirish
journalctl -u arabiy -f       # jonli log
```

## Zaxira nusxa va tiklash (K23.1)

Har kuni 03:00 (Toshkent) bot bazaning izchil nusxasini oladi: `/opt/arabiy/data/backups/arabiy-YYYY-MM-DD.db.gz`
(14 kun saqlanadi) va adminga Telegram hujjat sifatida yuboradi — serverdan tashqaridagi nusxa.
Qo'lda: `/zaxira`. Holat: `/tekshir` → «Zaxira: …».

Tiklash (masalan 2026-09-22 nusxasidan):

```bash
systemctl stop arabiy
cp /opt/arabiy/data/arabiy.db /opt/arabiy/data/arabiy.db.broken   # joriy holat ham qolsin
gunzip -c /opt/arabiy/data/backups/arabiy-2026-09-22.db.gz > /opt/arabiy/data/arabiy.db
rm -f /opt/arabiy/data/arabiy.db-wal /opt/arabiy/data/arabiy.db-shm
systemctl start arabiy
```

Telegram'dan olingan `.db.gz` faylni serverga `scp` qilib, xuddi shu buyruqlar bilan tiklash mumkin.

## Yangilanish (keyin kod o'zgarsa) — faqat git

`webapp/dist` git'da commit qilinadi — serverda build ham, tar arxiv ham kerak emas:

```bash
cd /opt/arabiy && git pull origin master && .venv/bin/pip install -q -r backend/requirements.txt && systemctl restart arabiy
```

yoki shu ishlarni bajaradigan skript: `sudo bash /opt/arabiy/deploy/update.sh`.

> ⚠️ Eski `/root/arabiy-deploy.tar.gz` arxivini ISHLATMANG va o'chirib yuboring (`rm -f /root/arabiy-deploy.tar.gz`) —
> u 2026-07 holatidagi kod; ustidan chiqarilsa butun sayt eski versiyaga qaytadi (2026-09-22 da shunday bo'lgan).
> Tiklash: `cd /opt/arabiy && git checkout -- . && git clean -fd backend webapp/dist content scripts deploy && git pull origin master && systemctl restart arabiy`.
