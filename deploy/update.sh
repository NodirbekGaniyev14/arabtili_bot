#!/usr/bin/env bash
# Arabiy botni yangilash — GIT orqali (webapp/dist commit qilinadi, serverda build shart emas).
# Serverda:  sudo bash /opt/arabiy/deploy/update.sh
#
# DIQQAT: eski (2026-07) versiya /root/arabiy-deploy.tar.gz arxivini ustidan yozardi —
# 2026-09-22 da shu sabab butun sayt iyul holatiga qaytib ketgan. Endi tar ishlatilmaydi.
set -e

APP_DIR=/opt/arabiy
cd "$APP_DIR"

echo "==> Git holati"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "   Diqqat: lokal o'zgargan kuzatiladigan fayllar bor — HEAD holatiga qaytariladi:"
  git status --short --untracked-files=no | head -20
  git checkout -- .
fi

echo "==> Yangi kod (git pull)"
git pull --ff-only origin master

echo "==> Bog'liqliklar"
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"

echo "==> Xizmat qayta ishga tushmoqda"
systemctl restart arabiy
sleep 3
systemctl --no-pager status arabiy | head -6 || true

echo ""
echo "==> Tekshirish"
curl -s http://127.0.0.1:8000/api/health && echo
echo -n "   webapp build: "
curl -s http://127.0.0.1:8000/ | grep -o 'assets/index-[A-Za-z0-9_-]*\.js' || echo "index.html o'qilmadi"
echo "   kutilgan:     $(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' webapp/dist/index.html)"
