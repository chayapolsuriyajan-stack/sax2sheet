from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sax2sheet.api.schemas import NoteOut
from sax2sheet.core.edits import EditOp, append_edit, apply_edits, clear_edits, load_edits, undo_last
from sax2sheet.core.storage import load_project
from sax2sheet.core.transcribe import load_notes

router = APIRouter(prefix="/api/projects/{project_id}/notes/edits", tags=["edits"])


class EditOpIn(BaseModel):
    op: str
    ids: list[str] = []
    pitch_midi: int | None = None
    onset_s: float | None = None
    offset_s: float | None = None
    semitones: int | None = None


def _current_notes(project) -> list[NoteOut]:
    raw = load_notes(project.notes_raw_json)
    edits = load_edits(project.notes_edits_json)
    return [asdict(n) for n in apply_edits(raw, edits)]


@router.get("", response_model=list[NoteOut])
def get_edits(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.notes_raw_json.exists():
        raise HTTPException(404, "no transcription yet")
    return _current_notes(project)


@router.post("", response_model=list[NoteOut])
def add_edit(project_id: str, op: EditOpIn):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.notes_raw_json.exists():
        raise HTTPException(404, "no transcription yet")

    try:
        edit = EditOp(**op.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    append_edit(project.notes_edits_json, edit)
    return _current_notes(project)


@router.post("/undo", response_model=list[NoteOut])
def undo(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    undo_last(project.notes_edits_json)
    return _current_notes(project)


@router.post("/clear", response_model=list[NoteOut])
def clear(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    clear_edits(project.notes_edits_json)
    return _current_notes(project)
