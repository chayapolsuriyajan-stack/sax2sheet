"""Audio ingestion: YouTube/URL download or local upload, normalized to a
44.1kHz mono WAV via ffmpeg so every downstream stage sees the same format.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from sax2sheet.core.storage import Project, get_or_create_project

TARGET_SAMPLE_RATE = 44100


def _ffmpeg_normalize(src: Path, dst: Path) -> None:
    """Convert any input audio/video file to mono 44.1kHz WAV."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it and ensure it's available "
            "as `ffmpeg` before ingesting audio."
        )
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ac", "1", "-ar", str(TARGET_SAMPLE_RATE),
        "-vn",  # drop any video stream
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg normalization failed:\n{result.stderr[-2000:]}")


def ingest_upload(upload_path: Path, original_filename: str) -> Project:
    """Normalize an already-saved upload and resolve it to a project."""
    with tempfile.TemporaryDirectory() as tmp:
        normalized = Path(tmp) / "normalized.wav"
        _ffmpeg_normalize(upload_path, normalized)
        return get_or_create_project(normalized, source_label=original_filename)


def ingest_url(url: str) -> Project:
    """Download audio from a YouTube link or other yt-dlp-supported URL,
    then normalize and resolve to a project.
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError as e:
        raise RuntimeError("yt-dlp is not installed") from e

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_template = str(tmp_path / "download.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "quiet": True,
            "noplaylist": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }],
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", url)

        downloaded = list(tmp_path.glob("download.*"))
        if not downloaded:
            raise RuntimeError("yt-dlp did not produce an output file")

        normalized = tmp_path / "normalized.wav"
        _ffmpeg_normalize(downloaded[0], normalized)
        return get_or_create_project(normalized, source_label=title)
