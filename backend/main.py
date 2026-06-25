"""
ระบบถอดเทปและสรุปการประชุม ยสท.
FastAPI Backend — main entry point

Routes:
  GET  /                        health check
  GET  /auth/login              เริ่ม Google OAuth flow
  GET  /auth/callback           รับ callback จาก Google
  GET  /auth/status             ตรวจสอบสถานะ login
  GET  /drive/files             ดึงรายการไฟล์จาก Drive
  POST /process/from-drive      ประมวลผลจากไฟล์ใน Drive
  POST /process/from-upload     ประมวลผลจากไฟล์ที่อัปโหลด
  GET  /process/status/{job_id} ตรวจสอบ progress
  POST /email/send              ส่งอีเมลรายงาน
  GET  /outputs/{filename}      ดาวน์โหลด PDF/DOCX
"""
import os
import uuid
import asyncio
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import (
    FastAPI, UploadFile, File, Form, HTTPException,
    BackgroundTasks, Request, Response
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import get_settings
from services.auth import (
    get_authorization_url, exchange_code_for_tokens,
    get_session_credentials, clear_session,
)
from services.drive import list_meeting_recordings, download_file
from services.transcribe import transcribe_audio, format_transcript_text
from services.summarize import summarize_meeting
from services.report import generate_pdf, generate_docx
from services.email import send_meeting_report

settings = get_settings()

# ---- Job store (in-memory) ----
# production ควรใช้ Redis หรือ database
jobs: dict[str, dict] = {}

# Railway Volume mount ที่ /data — fallback เป็น local outputs/
OUTPUTS_DIR = os.environ.get(
    "OUTPUTS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "outputs"),
)
os.makedirs(OUTPUTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌿 ระบบถอดเทปการประชุม ยสท. เริ่มทำงาน")
    yield
    print("🌿 ระบบหยุดทำงาน")


app = FastAPI(
    title="ระบบถอดเทปและสรุปการประชุม ยสท.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # production: ระบุ domain จริง
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# serve frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ===================== HEALTH =====================

@app.get("/")
def health():
    return {"status": "ok", "service": "ระบบถอดเทปการประชุม ยสท.", "version": "1.0.0"}


# ===================== AUTH =====================

@app.get("/auth/login")
def auth_login(session_id: Optional[str] = None):
    """เริ่ม Google OAuth — redirect ไปหน้า Google login"""
    result = get_authorization_url(session_id)
    return result


@app.get("/auth/callback")
def auth_callback(code: str, state: str, session_id: str, response: Response):
    """รับ callback จาก Google หลัง user login"""
    try:
        tokens = exchange_code_for_tokens(code, state, session_id)
        # redirect กลับ frontend
        return JSONResponse({"success": True, "session_id": session_id})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/status")
def auth_status(session_id: str):
    """ตรวจสอบว่า session มี credentials แล้วหรือยัง"""
    creds = get_session_credentials(session_id)
    return {"authenticated": creds is not None, "session_id": session_id}


@app.post("/auth/logout")
def auth_logout(session_id: str):
    clear_session(session_id)
    return {"success": True}


# ===================== DRIVE =====================

@app.get("/drive/files")
def get_drive_files(session_id: str, folder_id: Optional[str] = None):
    """ดึงรายการไฟล์การประชุมจาก Google Drive"""
    creds = get_session_credentials(session_id)
    if not creds:
        raise HTTPException(status_code=401, detail="กรุณา login Google ก่อน")
    try:
        files = list_meeting_recordings(creds, folder_id)
        return {"files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===================== MODELS =====================

class ProcessFromDriveRequest(BaseModel):
    session_id: str
    file_id: str
    agenda_items: list[str]
    meeting_title: str = "การประชุม ยสท."
    meeting_date: str = ""
    meeting_location: str = "ห้องประชุม ยสท."
    attendees: list[str] = []
    language: str = "th"
    output_formats: list[str] = ["pdf", "docx"]


class ProcessFromUploadRequest(BaseModel):
    session_id: str
    agenda_items: list[str]
    meeting_title: str = "การประชุม ยสท."
    meeting_date: str = ""
    meeting_location: str = "ห้องประชุม ยสท."
    attendees: list[str] = []
    language: str = "th"
    output_formats: list[str] = ["pdf", "docx"]


class SendEmailRequest(BaseModel):
    session_id: str
    job_id: str
    to_emails: list[str]
    subject: str
    body: str
    attach_pdf: bool = True
    attach_docx: bool = True
    attach_transcript: bool = False


# ===================== PROCESS =====================

def _update_job(job_id: str, step: str, status: str, data: dict = {}):
    """อัปเดต job status"""
    if job_id in jobs:
        jobs[job_id]["steps"][step] = status
        jobs[job_id].update(data)


async def _run_pipeline(
    job_id: str,
    audio_path: str,
    agenda_items: list[str],
    meeting_title: str,
    meeting_date: str,
    meeting_location: str,
    attendees: list[str],
    language: str,
    output_formats: list[str],
    openai_key: str,
    anthropic_key: str,
):
    """
    Pipeline หลัก: transcribe → summarize → generate reports
    รันเป็น background task
    """
    try:
        jobs[job_id]["status"] = "processing"

        # Step 1: Transcribe
        _update_job(job_id, "transcribe", "active")
        loop = asyncio.get_event_loop()
        transcript_result = await loop.run_in_executor(
            None,
            lambda: transcribe_audio(audio_path, language, openai_key),
        )
        transcript_text = format_transcript_text(transcript_result["segments"])
        _update_job(job_id, "transcribe", "done", {
            "transcript": transcript_text,
            "duration_sec": transcript_result["duration_sec"],
        })

        # Step 2: Summarize
        _update_job(job_id, "summarize", "active")
        summary_result = await loop.run_in_executor(
            None,
            lambda: summarize_meeting(
                transcript_text, agenda_items,
                meeting_date, meeting_title, anthropic_key,
            ),
        )
        _update_job(job_id, "summarize", "done", {"summary": summary_result})

        # Step 3: Generate reports
        _update_job(job_id, "report", "active")
        output_files = {}
        job_output_dir = os.path.join(OUTPUTS_DIR, job_id)
        os.makedirs(job_output_dir, exist_ok=True)

        if "pdf" in output_formats:
            pdf_path = os.path.join(job_output_dir, "รายงานการประชุม.pdf")
            await loop.run_in_executor(
                None,
                lambda: generate_pdf(
                    pdf_path, meeting_title, meeting_date,
                    meeting_location, attendees, agenda_items,
                    summary_result["summary_by_agenda"],
                    summary_result["action_items"],
                    transcript_text,
                ),
            )
            output_files["pdf"] = pdf_path

        if "docx" in output_formats:
            docx_path = os.path.join(job_output_dir, "รายงานการประชุม.docx")
            await loop.run_in_executor(
                None,
                lambda: generate_docx(
                    docx_path, meeting_title, meeting_date,
                    meeting_location, attendees, agenda_items,
                    summary_result["summary_by_agenda"],
                    summary_result["action_items"],
                ),
            )
            output_files["docx"] = docx_path

        # บันทึก transcript ด้วยเสมอ
        transcript_path = os.path.join(job_output_dir, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
        output_files["transcript"] = transcript_path

        _update_job(job_id, "report", "done", {"output_files": output_files})
        jobs[job_id]["status"] = "completed"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        raise


@app.post("/process/from-drive")
async def process_from_drive(
    req: ProcessFromDriveRequest,
    background_tasks: BackgroundTasks,
    openai_key: str = "",
    anthropic_key: str = "",
):
    """เริ่มประมวลผลจากไฟล์ใน Google Drive"""
    creds = get_session_credentials(req.session_id)
    if not creds:
        raise HTTPException(status_code=401, detail="กรุณา login Google ก่อน")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "preparing",
        "steps": {"download": "active", "transcribe": "pending",
                  "summarize": "pending", "report": "pending"},
    }

    async def _download_and_run():
        with tempfile.TemporaryDirectory() as tmp:
            try:
                _update_job(job_id, "download", "active")
                loop = asyncio.get_event_loop()
                audio_path = await loop.run_in_executor(
                    None,
                    lambda: download_file(creds, req.file_id, tmp),
                )
                _update_job(job_id, "download", "done")
                await _run_pipeline(
                    job_id, audio_path, req.agenda_items,
                    req.meeting_title, req.meeting_date,
                    req.meeting_location, req.attendees,
                    req.language, req.output_formats,
                    openai_key or settings.openai_api_key,
                    anthropic_key or settings.anthropic_api_key,
                )
            except Exception as e:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)

    background_tasks.add_task(_download_and_run)
    return {"job_id": job_id, "status": "started"}


@app.post("/process/from-upload")
async def process_from_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    agenda_items: str = Form(...),        # JSON string
    meeting_title: str = Form("การประชุม ยสท."),
    meeting_date: str = Form(""),
    meeting_location: str = Form("ห้องประชุม ยสท."),
    attendees: str = Form("[]"),          # JSON string
    language: str = Form("th"),
    output_formats: str = Form('["pdf","docx"]'),  # JSON string
    openai_key: str = Form(""),
    anthropic_key: str = Form(""),
):
    """เริ่มประมวลผลจากไฟล์ที่อัปโหลด"""
    import json

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "preparing",
        "steps": {"download": "done", "transcribe": "pending",
                  "summarize": "pending", "report": "pending"},
    }

    # บันทึกไฟล์ก่อน
    job_dir = os.path.join(OUTPUTS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    upload_path = os.path.join(job_dir, file.filename or "audio_upload")

    content = await file.read()
    with open(upload_path, "wb") as f:
        f.write(content)

    agenda = json.loads(agenda_items)
    fmt = json.loads(output_formats)
    att = json.loads(attendees)

    background_tasks.add_task(
        _run_pipeline,
        job_id, upload_path, agenda,
        meeting_title, meeting_date,
        meeting_location, att, language, fmt,
        openai_key or settings.openai_api_key,
        anthropic_key or settings.anthropic_api_key,
    )
    return {"job_id": job_id, "status": "started"}


@app.get("/process/status/{job_id}")
def get_job_status(job_id: str):
    """ตรวจสอบ progress ของ job"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ไม่พบ job นี้")

    # ไม่ส่ง path จริงออกไป แปลงเป็น download URL แทน
    output_urls = {}
    if "output_files" in job:
        for fmt, path in job["output_files"].items():
            filename = os.path.basename(path)
            output_urls[fmt] = f"/outputs/{job_id}/{filename}"

    return {
        "job_id": job_id,
        "status": job["status"],
        "steps": job.get("steps", {}),
        "transcript": job.get("transcript", ""),
        "summary": job.get("summary", {}),
        "output_urls": output_urls,
        "duration_sec": job.get("duration_sec"),
        "error": job.get("error"),
    }


# ===================== EMAIL =====================

@app.post("/email/send")
def send_email(req: SendEmailRequest):
    """ส่งอีเมลรายงานการประชุมพร้อมไฟล์แนบ"""
    creds = get_session_credentials(req.session_id)
    if not creds:
        raise HTTPException(status_code=401, detail="กรุณา login Google ก่อน")

    job = jobs.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล job")

    output_files = job.get("output_files", {})
    attachments = []
    if req.attach_pdf and "pdf" in output_files:
        attachments.append(output_files["pdf"])
    if req.attach_docx and "docx" in output_files:
        attachments.append(output_files["docx"])
    if req.attach_transcript and "transcript" in output_files:
        attachments.append(output_files["transcript"])

    try:
        result = send_meeting_report(
            credentials=creds,
            to_emails=req.to_emails,
            subject=req.subject,
            body_text=req.body,
            attachments=attachments,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===================== OUTPUTS =====================

@app.get("/outputs/{job_id}/{filename}")
def download_output(job_id: str, filename: str):
    """ดาวน์โหลดไฟล์รายงาน"""
    filepath = os.path.join(OUTPUTS_DIR, job_id, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")

    media_type = "application/pdf" if filename.endswith(".pdf") else \
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
                 if filename.endswith(".docx") else "text/plain"

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type=media_type,
    )


# ===================== RUN =====================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=port,
        reload=os.environ.get("ENVIRONMENT") == "development",
    )
