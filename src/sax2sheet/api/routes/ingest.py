from __future__ import annotations

import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from sax2sheet.api.schemas import IngestUrlRequest, ProjectSummary
from sax2sheet.config import settings
from sax2sheet.core.ingest import ingest_upload, ingest_url

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


@router.post("/upload", response_model=ProjectSummary)
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"unsupported file type: {ext or '(none)'}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / f"upload{ext}"
        size = 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
        with tmp_path.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"file exceeds {settings.max_upload_mb}MB limit")
                out.write(chunk)

        try:
            project = ingest_upload(tmp_path, file.filename or "upload")
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from e

    return asdict(project.load_manifest())


@router.post("/url", response_model=ProjectSummary)
def from_url(req: IngestUrlRequest):
    try:
        project = ingest_url(req.url)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    return asdict(project.load_manifest())
