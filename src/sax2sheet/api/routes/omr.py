from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from sax2sheet.api.schemas import ProjectSummary
from sax2sheet.config import settings
from sax2sheet.core.omr import SUPPORTED_OMR_SUFFIXES, is_available, scan_to_musicxml
from sax2sheet.core.score_import import import_score_upload

router = APIRouter(prefix="/api/omr", tags=["omr"])


@router.get("/capabilities")
def get_capabilities():
    return {"omr_available": is_available()}


@router.post("/upload", response_model=ProjectSummary)
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_OMR_SUFFIXES:
        raise HTTPException(
            400,
            f"unsupported file type: {ext or '(none)'} "
            f"(supported: {', '.join(sorted(SUPPORTED_OMR_SUFFIXES))})",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / f"scan{ext}"
        size = 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
        with tmp_path.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"file exceeds {settings.max_upload_mb}MB limit")
                out.write(chunk)

        try:
            musicxml_path = scan_to_musicxml(tmp_path)
            project = import_score_upload(musicxml_path, source_label=file.filename or "scan")
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from e

    return asdict(project.load_manifest())
