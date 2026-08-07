from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from sax2sheet.api.schemas import NoteOut, TranscribeRequest
from sax2sheet.core.storage import load_project
from sax2sheet.core.transcribe import load_notes, save_notes, transcribe_audio

router = APIRouter(prefix="/api/projects/{project_id}/notes", tags=["transcribe"])


@router.post("", response_model=list[NoteOut])
def transcribe(project_id: str, req: TranscribeRequest):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")

    audio_path = project.stem_wav(req.stem) if req.stem else project.source_wav
    if not audio_path.exists():
        raise HTTPException(400, f"audio not available for stem={req.stem!r}; separate first")

    notes = transcribe_audio(
        audio_path,
        onset_threshold=req.onset_threshold,
        frame_threshold=req.frame_threshold,
        minimum_note_length_ms=req.minimum_note_length_ms,
    )
    save_notes(notes, project.notes_raw_json)

    manifest = project.load_manifest()
    manifest.stages["transcribed"] = True
    manifest.active_stem = req.stem
    project.save_manifest(manifest)

    return [asdict(n) for n in notes]


@router.get("", response_model=list[NoteOut])
def get_notes(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.notes_raw_json.exists():
        raise HTTPException(404, "no transcription yet")
    return [asdict(n) for n in load_notes(project.notes_raw_json)]
