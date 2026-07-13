#!/usr/bin/env bash
# Arabiy botni yangilash (kod o'zgargach).
# 1) Yangi arabiy-deploy.tar.gz ni serverga /root/ ga scp qiling
# 2) Serverda:  sudo bash /opt/arabiy/deploy/update.sh
set -e

APP_DIR=/opt/arabiy
TARBALL=/root/arabiy-deploy.tar.gz

echo "==> Xizmat to'xtatilmoqda"
systemctl stop arabiy

echo "==> Yangi kod ochilmoqda (ma'lumotlar bazasiga tegilmaydi)"
tar -xzf "$TARBALL" -C "$APP_DIR"

echo "==> Bog'liqliklar tekshirilmoqda"
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"

echo "==> Xizmat qayta ishga tushmoqda"
systemctl start arabiy
sleep 3
systemctl --no-pager status arabiy | head -6 || true

echo ""
echo "==> Tekshirish"
curl -s http://127.0.0.1:8000/api/health && echo
