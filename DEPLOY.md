# คู่มือ Deploy ระบบถอดเทปการประชุม ยสท.

## ภาพรวม

```
GitHub (โค้ด)
    ├── Railway  → Backend FastAPI  → ysot-api.railway.app
    └── Vercel   → Frontend HTML   → ysot-meeting.vercel.app
```

---

## ขั้นตอนที่ 1 — Upload โค้ดไป GitHub

```bash
# 1. สร้าง repo ใหม่บน github.com ชื่อ ysot-meeting
# 2. รันคำสั่งต่อไปนี้ในโฟลเดอร์โปรเจกต์

git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/ysot-meeting.git
git push -u origin main
```

---

## ขั้นตอนที่ 2 — Deploy Backend ไป Railway

### 2.1 สมัคร Railway
1. ไปที่ https://railway.app
2. คลิก **Login with GitHub**
3. ยืนยัน email

### 2.2 สร้าง Project
1. คลิก **New Project**
2. เลือก **Deploy from GitHub repo**
3. เลือก repo `ysot-meeting`
4. Railway จะตรวจเจอ `Dockerfile` อัตโนมัติ

### 2.3 ตั้งค่า Environment Variables
ไปที่ **Variables** tab แล้วเพิ่มทีละตัว:

```
OPENAI_API_KEY        = sk-...
ANTHROPIC_API_KEY     = sk-ant-...
GOOGLE_CLIENT_ID      = xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET  = GOCSPX-...
MEET_RECORDINGS_FOLDER_ID = 1AbCdEfGh...
SENDER_EMAIL          = meeting@thaitobacco.or.th
SENDER_NAME           = ระบบการประชุม ยสท.
OUTPUTS_DIR           = /data/outputs
```

### 2.4 เพิ่ม Volume (เก็บไฟล์รายงาน)
1. ไปที่ **Volumes** tab
2. คลิก **Add Volume**
3. ตั้ง Mount Path: `/data`
4. ขนาด: 5 GB (เพียงพอ)

### 2.5 รับ Railway URL
หลัง deploy เสร็จ ไปที่ **Settings → Domains**
จะได้ URL เช่น `https://ysot-meeting-production.up.railway.app`

### 2.6 อัปเดต Google OAuth Redirect URI
1. ไปที่ Google Cloud Console → Credentials
2. แก้ OAuth Client → เพิ่ม Authorized redirect URIs:
   ```
   https://ysot-meeting-production.up.railway.app/auth/callback
   ```
3. อัปเดต Railway env var:
   ```
   GOOGLE_REDIRECT_URI = https://ysot-meeting-production.up.railway.app/auth/callback
   ```

---

## ขั้นตอนที่ 3 — Deploy Frontend ไป Vercel

### 3.1 สมัคร Vercel
1. ไปที่ https://vercel.com
2. คลิก **Continue with GitHub**

### 3.2 Import Project
1. คลิก **Add New → Project**
2. Import repo `ysot-meeting`
3. **Root Directory**: ตั้งเป็น `frontend`
4. คลิก **Deploy**

### 3.3 ตั้งค่า Backend URL
ไปที่ **Settings → Environment Variables** เพิ่ม:
```
BACKEND_URL = https://ysot-meeting-production.up.railway.app
```

**สำคัญ**: แก้ไข `frontend/index.html` บรรทัดนี้:
```javascript
const API_BASE = window.BACKEND_URL || 'https://ysot-meeting-production.up.railway.app';
```
แทนที่ URL ด้วย Railway URL จริงของคุณ แล้ว push ไป GitHub อีกครั้ง

---

## ขั้นตอนที่ 4 — ตรวจสอบระบบ

### ทดสอบ Backend
```bash
# Health check
curl https://ysot-meeting-production.up.railway.app/

# ควรได้:
# {"status":"ok","service":"ระบบถอดเทปการประชุม ยสท.","version":"1.0.0"}
```

### ทดสอบ Frontend
เปิด https://ysot-meeting.vercel.app
- ควรเห็นหน้า UI ของระบบ
- กด Login Google → ควรเด้ง popup ขอ permission

---

## ค่าใช้จ่ายต่อเดือน (โดยประมาณ)

| บริการ | ค่าใช้จ่าย |
|--------|-----------|
| Railway (Starter plan) | ฟรี $5 credit ≈ 500 ชั่วโมง |
| Vercel (Hobby) | ฟรี |
| OpenAI Whisper | ~$0.36/ชั่วโมงการประชุม |
| Anthropic Claude | ~$0.05/การประชุม |
| Google APIs | ฟรี |
| **รวมถ้าประชุม 10 ครั้ง/เดือน** | **~$4-5 (ประมาณ 150 บาท)** |

---

## ปัญหาที่พบบ่อย

**Q: Railway deploy ไม่ผ่าน**
- ตรวจสอบ `Dockerfile` syntax
- ดู Build logs ใน Railway dashboard

**Q: Google OAuth ไม่ทำงาน**  
- ตรวจสอบ Redirect URI ตรงกันทุกตัวอักษร
- ตรวจสอบว่า Drive API และ Gmail API เปิดใช้งานแล้ว

**Q: PDF ภาษาไทยแสดงไม่ถูกต้อง**  
- ตรวจสอบ Sarabun font ดาวน์โหลดสำเร็จตอน build
- ดู Docker build logs หา `wget` error

**Q: Whisper timeout สำหรับไฟล์ใหญ่**  
- Railway Starter ไม่มี timeout — ไฟล์ใหญ่แค่ไหนก็ประมวลผลได้
- ถ้าช้ามาก ให้ upgrade เป็น Pro plan
