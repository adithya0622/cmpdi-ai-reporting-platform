FROM node:20-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       tesseract-ocr-hin \
       libreoffice-writer \
       libpq-dev \
       gcc \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/data/hf \
    SENTENCE_TRANSFORMERS_HOME=/data/models

WORKDIR /app
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /web/dist /app/app/static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
