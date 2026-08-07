from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from sax2sheet.api.schemas import ProjectSummary
from sax2sheet.core.storage import list_projects, load_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def get_projects():
    return [asdict(m) for m in list_projects()]


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    manifest = project.load_manifest()
    return asdict(manifest)
