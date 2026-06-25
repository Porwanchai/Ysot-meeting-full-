# ระบบถอดเทปและสรุปการประชุม ยสท.

ระบบอัตโนมัติสำหรับถอดเทปไฟล์เสียง/วิดีโอจาก Google Meet  
สรุปตามวาระการประชุม และส่งรายงานให้ผู้เข้าร่วมทางอีเมล

---

## โครงสร้างโปรเจกต์

```
ysot-meeting/
├── backend/
│   ├── main.py                 # FastAPI app หลัก
│   ├── config.py               # Settings & constants
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example            # ตัวอย่าง env variables
│   ├── fonts/                  # Sarabun font files (ดาวน์โหลดเพิ่ม)
│   └── services/
│       ├── auth.py             # Google OAuth2
│       ├── drive.py            # Google Drive API
│       ├── transcribe.py       # OpenAI Whisper
│       ├── summarize.py        # Anthropic Claude
│       ├── report.py           # PDF + DOCX generator
│       └── email.py            # Gmail API
├── frontend/
│   └── index.html              # Web UI
└── outputs/                    # ไฟล์ผลลัพธ์ (auto-created)
```

---

## ขั้นตอนการติดตั้ง

### 1. ติดตั้ง Python dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. ติดตั้ง ffmpeg (จำเป็นสำหรับแปลงเสียง)

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows — ดาวน์โหลดจาก https://ffmpeg.org/download.html
```

### 3. ดาวน์โหลด Sarabun font (สำหรับ PDF ภาษาไทย)

```bash
mkdir -p backend/fonts
# ดาวน์โหลดจาก Google Fonts
curl -L "https://fonts.gstatic.com/s/sarabun/v15/DtVmJx26TKEr37c9YHZJmg.ttf" \
     -o backend/fonts/Sarabun-Regular.ttf
curl -L "https://fonts.gstatic.com/s/sarabun/v15/DtVhJx26TKEr37c9aBBJn18.ttf" \
     -o backend/fonts/Sarabun-Bold.ttf
```

### 4. ตั้งค่า Google Cloud Project

1. ไปที่ https://console.cloud.google.com
2. สร้าง Project ใหม่ (หรือใช้ Project ของ ยสท. ที่มีอยู่)
3. เปิดใช้งาน APIs:
   - Google Drive API
   - Gmail API
   - Google Picker API
4. สร้าง OAuth 2.0 Client ID (Web Application)
   - Authorized redirect URIs: `http://localhost:8000/auth/callback`
5. สร้าง API Key (สำหรับ Google Picker)
6. ถ้าเป็น Google Workspace — ตั้งค่า restrict domain เป็น `@thaitobacco.or.th`

### 5. ตั้งค่า .env

```bash
cp .env.example .env
# แก้ไขค่าใน .env ด้วย credentials จากข้อ 4
```

### 6. ดึง folder ID ของ Meet Recordings

1. เปิด Google Drive → ค้นหา folder "Meet Recordings"
2. คลิกเข้า folder แล้วดู URL:
   `https://drive.google.com/drive/folders/`**`1AbCdEfGh...`**
3. นำ ID นั้นใส่ใน `.env` → `MEET_RECORDINGS_FOLDER_ID`

---

## การรันระบบ

```bash
cd backend
source venv/bin/activate
python main.py
```

เปิด browser: `http://localhost:8000/app`

---

## API Endpoints

| Method | Path | หน้าที่ |
|--------|------|---------|
| GET | `/` | Health check |
| GET | `/auth/login` | เริ่ม Google login |
| GET | `/auth/callback` | รับ token จาก Google |
| GET | `/auth/status` | ตรวจสอบสถานะ login |
| GET | `/drive/files` | รายการไฟล์ใน Drive |
| POST | `/process/from-drive` | ประมวลผลจาก Drive |
| POST | `/process/from-upload` | ประมวลผลจากไฟล์อัปโหลด |
| GET | `/process/status/{job_id}` | ตรวจสอบ progress |
| POST | `/email/send` | ส่งอีเมลรายงาน |
| GET | `/outputs/{job_id}/{filename}` | ดาวน์โหลดรายงาน |

---

## ค่าใช้จ่าย API (โดยประมาณ)

| การประชุม 1 ชั่วโมง | ค่าใช้จ่าย |
|---------------------|-----------|
| Whisper API | ~$0.36 (~13 บาท) |
| Claude API (สรุป) | ~$0.05 (~2 บาท) |
| Google APIs | ฟรี |
| **รวม** | **~15 บาท/ครั้ง** |

---

## ความปลอดภัย

- ไฟล์เสียงส่งไป Whisper API เท่านั้น (ไม่บันทึกถาวรโดย OpenAI)
- Transcript (ข้อความ) ส่งไป Claude API เพื่อสรุป
- ไฟล์ต้นฉบับและรายงานเก็บใน server ยสท.
- ใช้ Google OAuth2 — ไม่มีการเก็บ password
- production: เปลี่ยน in-memory session เป็น Redis
