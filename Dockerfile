# ── 1-bosqich: Mini App build ──
FROM node:22-alpine AS webapp
WORKDIR /app/webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/ ./
RUN npm run build

# ── 2-bosqich: Python server ──
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY content/ content/
COPY --from=webapp /app/webapp/dist webapp/dist

ENV PYTHONUNBUFFERED=1

# Railway PORT beradi; lokal docker uchun 8000
CMD ["sh", "-c", "python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
