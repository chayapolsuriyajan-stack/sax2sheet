from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sax2sheet.api.routes import edits, import_score, ingest, omr, projects, score, separate, transcribe
from sax2sheet.core.storage import load_project

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="sax2sheet")

app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(import_score.router)
app.include_router(omr.router)
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


class RevalidatingStaticFiles(StaticFiles):
    """StaticFiles serves no Cache-Control header by default, which leaves
    browsers free to apply *heuristic* caching -- serving JS/CSS straight
    from disk cache without even a conditional request, for a duration the
    browser picks itself. That's a real correctness risk here, not just a
    dev-loop annoyance: this app changes frequently, and `run.bat`'s
    "restart server, refresh browser" workflow can otherwise leave a viewer
    running stale JS against a newer API. `no-cache` forces revalidation
    (an If-None-Match round trip) on every load; the existing ETag still
    makes that cheap when nothing changed.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Static frontend last, so /api/* above takes precedence.
app.mount("/", RevalidatingStaticFiles(directory=WEB_DIR, html=True), name="web")
