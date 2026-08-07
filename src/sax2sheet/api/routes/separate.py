from __future__ import annotations

from fastapi import APIRouter, HTTPException

from sax2sheet.core.separate import available_stems, separate_project
from sax2sheet.core.storage import load_project

router = APIRouter(prefix="/api/projects/{project_id}/separate", tags=["separate"])


@router.post("")
def separate(project_id: str, force: bool = False):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.source_wav.exists():
        raise HTTPException(400, "no audio to separate")

    try:
        stems = separate_project(project, force=force)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e

    return {"stems": stems}


@router.get("")
def get_stems(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return {"stems": available_stems(project)}
