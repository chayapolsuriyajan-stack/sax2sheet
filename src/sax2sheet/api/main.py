from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sax2sheet.api.routes import edits, ingest, projects, score, separate, transcribe
from sax2sheet.core.storage import load_project

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="sax2sheet")

app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(transcribe.router)
app.include_router(edits.router)
app.include_router(score.router)
app.include_router(separate.router)


@app.get("/api/projects/{project_id}/audio")
def get_audio(project_id: str, stem: str | None = None):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    path = project.stem_wav(stem) if stem else project.source_wav
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav")


# Static frontend last, so /api/* above takes precedence.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
