"""
Transcription Service (OpenAI Whisper)
- ตัดไฟล์เสียงเป็น chunk ถ้าใหญ่เกิน 25MB
- ถอดเทปพร้อม timestamp และแยกภาษา
- รวม chunk กลับเป็น transcript เดียว
"""
import os
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from openai import OpenAI

from config import get_settings, WHISPER_MAX_MB, WHISPER_MODEL

settings = get_settings()


def _get_audio_duration(filepath: str) -> float:
    """ดึงความยาวเสียงด้วย ffprobe (วินาที)"""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _extract_audio(input_path: str, output_path: str) -> str:
    """แปลงวิดีโอเป็นเสียง mp3 ด้วย ffmpeg"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-vn",                   # ไม่เอาวิดีโอ
            "-ar", "16000",          # 16kHz เหมาะกับ Whisper
            "-ac", "1",              # mono
            "-b:a", "64k",           # bitrate ต่ำเพื่อลด size
            output_path,
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def _split_audio(audio_path: str, chunk_duration_sec: int, tmp_dir: str) -> list[str]:
    """ตัดไฟล์เสียงเป็น chunks"""
    duration = _get_audio_duration(audio_path)
    num_chunks = math.ceil(duration / chunk_duration_sec)
    chunk_paths = []

    for i in range(num_chunks):
        start = i * chunk_duration_sec
        out = os.path.join(tmp_dir, f"chunk_{i:03d}.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ss", str(start),
                "-t", str(chunk_duration_sec),
                "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
                out,
            ],
            check=True,
            capture_output=True,
        )
        chunk_paths.append(out)

    return chunk_paths


def _whisper_transcribe_file(
    client: OpenAI,
    audio_path: str,
    language: str,
    time_offset_sec: float = 0.0,
) -> list[dict]:
    """
    ส่งไฟล์หนึ่งไป Whisper แล้วคืน list ของ segments
    แต่ละ segment: {start, end, text}
    """
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            language=language if language != "th-en" else "th",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    for seg in (response.segments or []):
        segments.append({
            "start": round(seg.start + time_offset_sec, 1),
            "end": round(seg.end + time_offset_sec, 1),
            "text": seg.text.strip(),
        })
    return segments


def transcribe_audio(
    file_path: str,
    language: str = "th",
    openai_api_key: Optional[str] = None,
) -> dict:
    """
    Main function: ถอดเทปไฟล์เสียง/วิดีโอ
    คืนค่า: {segments, full_text, duration}
    """
    api_key = openai_api_key or settings.openai_api_key
    client = OpenAI(api_key=api_key)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. แปลงเป็น mp3 ก่อนเสมอ (รองรับ mp4, m4a, wav ฯลฯ)
        audio_path = os.path.join(tmp_dir, "audio.mp3")
        _extract_audio(file_path, audio_path)

        # 2. ตรวจ size — ถ้าใหญ่เกิน threshold ให้ตัด chunk
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        duration_total = _get_audio_duration(audio_path)

        # คำนวณ chunk duration จาก bitrate 64kbps
        # 64kbps = 8KB/s → 24MB ≈ 3000 วินาที (50 นาที)
        chunk_duration = int(WHISPER_MAX_MB * 1024 * 1024 / (64 * 1024 / 8))

        all_segments: list[dict] = []

        if file_size_mb <= WHISPER_MAX_MB:
            # ไฟล์เล็ก ส่งตรง
            all_segments = _whisper_transcribe_file(client, audio_path, language)
        else:
            # ไฟล์ใหญ่ ตัด chunk
            chunk_paths = _split_audio(audio_path, chunk_duration, tmp_dir)
            for i, chunk_path in enumerate(chunk_paths):
                offset = i * chunk_duration
                segs = _whisper_transcribe_file(client, chunk_path, language, offset)
                all_segments.extend(segs)

        # 3. รวมเป็น full text
        full_text = " ".join(seg["text"] for seg in all_segments)

        return {
            "segments": all_segments,
            "full_text": full_text,
            "duration_sec": round(duration_total, 1),
            "language": language,
        }


def format_transcript_text(segments: list[dict], with_timestamp: bool = True) -> str:
    """
    จัดรูปแบบ transcript สำหรับแสดงผลและส่งให้ Claude
    รูปแบบ: [MM:SS] ข้อความ
    """
    lines = []
    for seg in segments:
        if with_timestamp:
            minutes = int(seg["start"] // 60)
            seconds = int(seg["start"] % 60)
            ts = f"[{minutes:02d}:{seconds:02d}]"
            lines.append(f"{ts} {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)
