"""
Transcription Service
- รองรับทั้ง OpenAI Whisper และ Groq Whisper
- ตัดไฟล์เสียงเป็น chunk ถ้าใหญ่เกิน 25MB
"""
import os
import math
import subprocess
import tempfile

from config import get_settings

settings = get_settings()


def _get_audio_duration(filepath: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", filepath],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _extract_audio(input_path: str, output_path: str) -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path,
         "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k", output_path],
        check=True, capture_output=True,
    )
    return output_path


def _split_audio(audio_path: str, chunk_sec: int, tmp_dir: str) -> list[str]:
    duration = _get_audio_duration(audio_path)
    num_chunks = math.ceil(duration / chunk_sec)
    chunks = []
    for i in range(num_chunks):
        out = os.path.join(tmp_dir, f"chunk_{i:03d}.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path,
             "-ss", str(i * chunk_sec), "-t", str(chunk_sec),
             "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k", out],
            check=True, capture_output=True,
        )
        chunks.append(out)
    return chunks


def _parse_segments(response, offset: float = 0.0) -> list[dict]:
    """
    แยก segments จาก response ของทั้ง OpenAI และ Groq
    รองรับทั้ง object และ dict
    """
    segments = []

    # ดึง segments จาก response
    raw_segs = None
    if hasattr(response, "segments"):
        raw_segs = response.segments
    elif isinstance(response, dict):
        raw_segs = response.get("segments", [])

    if not raw_segs:
        # ถ้าไม่มี segments ใช้ text ทั้งหมดแทน
        text = ""
        if hasattr(response, "text"):
            text = response.text
        elif isinstance(response, dict):
            text = response.get("text", "")
        if text:
            segments.append({"start": offset, "end": offset + 30, "text": text.strip()})
        return segments

    for s in raw_segs:
        try:
            # รองรับทั้ง object (OpenAI) และ dict (Groq)
            if isinstance(s, dict):
                start = float(s.get("start", 0))
                end = float(s.get("end", 0))
                text = str(s.get("text", "")).strip()
            else:
                start = float(getattr(s, "start", 0))
                end = float(getattr(s, "end", 0))
                text = str(getattr(s, "text", "")).strip()

            if text:
                segments.append({
                    "start": round(start + offset, 1),
                    "end": round(end + offset, 1),
                    "text": text,
                })
        except Exception:
            continue

    return segments


def _transcribe_with_openai(audio_path: str, language: str, offset: float = 0.0) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language if language != "th-en" else "th",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    return _parse_segments(response, offset)


def _transcribe_with_groq(audio_path: str, language: str, offset: float = 0.0) -> list[dict]:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)

    lang = language if language != "th-en" else "th"

    with open(audio_path, "rb") as f:
        # Groq: ใช้ verbose_json เพื่อได้ segments
        response = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            language=lang,
            response_format="verbose_json",
        )

    return _parse_segments(response, offset)


def transcribe_audio(
    file_path: str,
    language: str = "th",
    openai_api_key: str | None = None,
) -> dict:
    """ถอดเทปไฟล์เสียง/วิดีโอ — เลือก provider จาก WHISPER_PROVIDER env var"""
    provider = os.environ.get("WHISPER_PROVIDER", "openai").lower()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # แปลงเป็น mp3
        audio_path = os.path.join(tmp_dir, "audio.mp3")
        _extract_audio(file_path, audio_path)

        duration_total = _get_audio_duration(audio_path)
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        chunk_sec = int(24 * 1024 * 1024 / (64 * 1024 / 8))  # ~50 นาที

        def do_transcribe(path, offset=0.0):
            if provider == "groq":
                return _transcribe_with_groq(path, language, offset)
            return _transcribe_with_openai(path, language, offset)

        all_segments = []
        if file_size_mb <= 24:
            all_segments = do_transcribe(audio_path)
        else:
            for i, chunk in enumerate(_split_audio(audio_path, chunk_sec, tmp_dir)):
                all_segments.extend(do_transcribe(chunk, i * chunk_sec))

        return {
            "segments": all_segments,
            "full_text": " ".join(s["text"] for s in all_segments),
            "duration_sec": round(duration_total, 1),
            "language": language,
            "provider": provider,
        }


def format_transcript_text(segments: list[dict], with_timestamp: bool = True) -> str:
    lines = []
    for seg in segments:
        if with_timestamp:
            m, s = int(seg["start"] // 60), int(seg["start"] % 60)
            lines.append(f"[{m:02d}:{s:02d}] {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)
