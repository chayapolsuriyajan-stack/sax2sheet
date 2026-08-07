from __future__ import annotations

from fastapi import APIRouter, HTTPException

from sax2sheet.core.separate import available_stems, gpu_available, is_available, separate_project
from sax2sheet.core.storage import load_project

router = APIRouter(prefix="/api/projects/{project_id}/separate", tags=["separate"])


@router.post("")
def separate(project_id: str, force: bool = False, device: str = "auto"):
    if device not in ("auto", "cpu", "cuda"):
        raise HTTPException(400, "device must be one of: auto, cpu, cuda")

    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.source_wav.exists():
        raise HTTPException(400, "no audio to separate")

    try:
        stems = separate_project(project, force=force, device=device)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e

    return {"stems": stems}


@router.get("")
def get_stems(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return {"stems": available_stems(project)}


@router.get("/capabilities")
def get_capabilities(project_id: str):
    """Lets the frontend show/hide the GPU toggle without guessing: reports
    whether Demucs is installed at all and whether torch sees a CUDA GPU.
    """
    return {"demucs_available": is_available(), "gpu_available": gpu_available() if is_available() else False}
