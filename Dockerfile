FROM python:3.11-slim

# ติดตั้ง ffmpeg + font dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    fontconfig \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# ดาวน์โหลด Sarabun font สำหรับ PDF ภาษาไทย
RUN mkdir -p /app/backend/fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf" \
         -O /app/backend/fonts/Sarabun-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Bold.ttf" \
         -O /app/backend/fonts/Sarabun-Bold.ttf && \
    fc-cache -f -v

WORKDIR /app

# ติดตั้ง Python dependencies ก่อน (cache layer)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# copy source code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# สร้าง outputs directory
RUN mkdir -p /app/outputs

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
