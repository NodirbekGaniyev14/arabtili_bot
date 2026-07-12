#!/usr/bin/env bash
# Arabiy botni serverga o'rnatish skripti.
# Frontend allaqachon build qilingan (webapp/dist arxivda) — serverda Node kerak emas.
# Serverda /opt/arabiy papkasida ishga tushiring:
#   cd /opt/arabiy && sudo bash deploy/setup.sh
set -e

APP_DIR=/opt/arabiy
cd "$APP_DIR"

echo "==> 1/4  Tizim paketlari (python venv, nginx, certbot)"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip nginx certbot python3-certbot-nginx curl

echo "==> 2/4  Python virtual muhiti va bog'liqliklar"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r backend/requirements.txt

echo "==> 3/4  Ma'lumotlar papkasi"
mkdir -p "$APP_DIR/data"

echo "==> 4/4  systemd xizmati"
cp deploy/arabiy.service /etc/systemd/system/arabiy.service
systemctl daemon-reload
systemctl enable arabiy
systemctl restart arabiy

echo ""
echo "✅ Backend o'rnatildi. Holat:"
sleep 3
systemctl --no-pager status arabiy | head -6 || true
echo ""
echo "Tekshirish: curl http://127.0.0.1:8000/api/health"
echo "Keyingi qadam: nginx server bloki + certbot (DEPLOY.md 3–4 qadam)."
