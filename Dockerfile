FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg wget curl fontconfig \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/backend/fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf" \
         -O /app/backend/fonts/Sarabun-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf" \
         -O /app/backend/fonts/Sarabun-Bold.ttf && \
    fc-cache -f -v

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# CACHE_BUST: force copy fresh source code
ARG CACHE_BUST=1
COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN mkdir -p /app/outputs

WORKDIR /app/backend

# verify auth.py ไม่มี nonce
RUN python3 -c "
import ast
with open('services/auth.py') as f:
    src = f.read()
assert 'nonce' not in src, 'ERROR: old auth.py with nonce detected!'
print('OK: auth.py is clean')
"

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
