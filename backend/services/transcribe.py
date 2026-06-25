"""
Transcription Service
- รองรับทั้ง OpenAI Whisper และ Groq Whisper
- ตัดไฟล์เสียงเป็น chunk ถ้าใหญ่เกิน limit
- รวม chunk กลับเป็น transcript เดียว
"""
import os
import math
import subprocess
import tempfile

from config import get_settings, WHISPER_MAX_MB, WHISPER_MODEL

settings = get_settings()

# Groq limit อยู่ที่ 25MB เหมือนกัน
GROQ_MAX_MB = 24


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


def _transcribe_with_openai(audio_path: str, language: str, offset: float = 0.0) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language=language if language != "th-en" else "th",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    return [
        {"start": round(s.start + offset, 1),
         "end": round(s.end + offset, 1),
         "text": s.text.strip()}
        for s in (response.segments or [])
    ]


def _transcribe_with_groq(audio_path: str, language: str, offset: float = 0.0) -> list[dict]:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            language=language if language != "th-en" else "th",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments = []
    for s in (response.segments or []):
        segments.append({
            "start": round(s.start + offset, 1),
            "end": round(s.end + offset, 1),
            "text": s.text.strip(),
        })
    return segments


def transcribe_audio(
    file_path: str,
    language: str = "th",
    openai_api_key: str | None = None,
) -> dict:
    """
    ถอดเทปไฟล์เสียง/วิดีโอ
    เลือก provider จาก WHISPER_PROVIDER env var (openai หรือ groq)
    """
    provider = os.environ.get("WHISPER_PROVIDER", "openai").lower()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # แปลงเป็น mp3
        audio_path = os.path.join(tmp_dir, "audio.mp3")
        _extract_audio(file_path, audio_path)

        duration_total = _get_audio_duration(audio_path)
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

        # chunk duration ~50 นาที ที่ 64kbps
        chunk_sec = int(24 * 1024 * 1024 / (64 * 1024 / 8))

        def transcribe_file(path, offset=0.0):
            if provider == "groq":
                return _transcribe_with_groq(path, language, offset)
            else:
                return _transcribe_with_openai(path, language, offset)

        all_segments = []
        if file_size_mb <= 24:
            all_segments = transcribe_file(audio_path)
        else:
            for i, chunk in enumerate(_split_audio(audio_path, chunk_sec, tmp_dir)):
                all_segments.extend(transcribe_file(chunk, i * chunk_sec))

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
