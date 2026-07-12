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

## Yangilanish (keyin kod o'zgarsa)

```bash
# Kompyuterdan yangi arxiv yuboring, keyin serverda:
tar -xzf /root/arabiy-deploy.tar.gz -C /opt/arabiy
cd /opt/arabiy/webapp && npm run build && cd ..
systemctl restart arabiy
```
