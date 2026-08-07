from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from sax2sheet.api.schemas import AnalysisOut, ExportOut, ScoreOut, ScoreSettingsIn
from sax2sheet.core.analyze import analyze_audio
from sax2sheet.core.edits import apply_edits, load_edits
from sax2sheet.core.models import Instrument, NoteEvent, QuantizeSettings
from sax2sheet.core.notation import build_score, export_midi, export_musicxml, score_to_json_model
from sax2sheet.core.quantize import quantize_notes
from sax2sheet.core.storage import Project, load_project
from sax2sheet.core.transcribe import load_notes
from sax2sheet.core.transpose import transpose_key_signature, transpose_notes

router = APIRouter(prefix="/api/projects/{project_id}", tags=["score"])


def _compute_transposed_notes(
    project: Project, settings: ScoreSettingsIn
) -> tuple[list[NoteEvent], int, Instrument]:
    """Shared pipeline: raw notes -> edits -> quantize -> transpose. Used by
    both the score preview and the export endpoints so they can never drift
    apart.
    """
    try:
        instrument = Instrument(settings.instrument)
    except ValueError as e:
        raise HTTPException(400, f"unknown instrument: {settings.instrument!r}") from e

    raw = load_notes(project.notes_raw_json)
    edits = load_edits(project.notes_edits_json)
    current = [n for n in apply_edits(raw, edits) if not n.deleted]

    qs = QuantizeSettings(**settings.quantize.model_dump())
    quantized = quantize_notes(current, qs)
    transposed = transpose_notes(quantized, instrument, settings.global_octave_shift)

    concert_sharps = 0
    if project.analysis_json.exists():
        concert_sharps = json.loads(project.analysis_json.read_text())["key_sharps"]
    written_sharps = transpose_key_signature(concert_sharps, instrument)

    return transposed, written_sharps, instrument


def _require_transcribed_project(project_id: str) -> Project:
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.notes_raw_json.exists():
        raise HTTPException(404, "no transcription yet")
    return project


@router.post("/analyze", response_model=AnalysisOut)
def analyze(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.source_wav.exists():
        raise HTTPException(400, "no audio to analyze")

    result = analyze_audio(project.source_wav)
    project.analysis_json.write_text(json.dumps(asdict(result), indent=2))

    manifest = project.load_manifest()
    manifest.stages["analyzed"] = True
    project.save_manifest(manifest)

    return asdict(result)


@router.get("/analyze", response_model=AnalysisOut)
def get_analysis(project_id: str):
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if not project.analysis_json.exists():
        raise HTTPException(404, "not analyzed yet")
    return json.loads(project.analysis_json.read_text())


@router.post("/score", response_model=ScoreOut)
def compute_score(project_id: str, settings: ScoreSettingsIn):
    project = _require_transcribed_project(project_id)
    transposed, written_sharps, _ = _compute_transposed_notes(project, settings)
    return {
        "notes": [asdict(n) for n in transposed],
        "key_sharps": written_sharps,
    }


@router.post("/export", response_model=ExportOut)
def export_score(project_id: str, settings: ScoreSettingsIn):
    project = _require_transcribed_project(project_id)
    transposed, written_sharps, instrument = _compute_transposed_notes(project, settings)

    instrument_names = {
        "soprano": "Soprano Saxophone",
        "alto": "Alto Saxophone",
        "tenor": "Tenor Saxophone",
        "baritone": "Baritone Saxophone",
    }
    bpm = settings.quantize.bpm
    time_sig = settings.quantize.time_signature

    m21_score = build_score(
        transposed, written_sharps, bpm, time_sig, instrument_names.get(settings.instrument, "Saxophone")
    )
    export_musicxml(m21_score, project.export_path("musicxml"))
    export_midi(m21_score, project.export_path("mid"))

    score_model = score_to_json_model(transposed, written_sharps, bpm, time_sig)

    return {
        "score_model": score_model,
        "musicxml_url": f"/api/projects/{project_id}/export/musicxml",
        "midi_url": f"/api/projects/{project_id}/export/mid",
    }


@router.get("/export/{fmt}")
def download_export(project_id: str, fmt: str):
    if fmt not in ("musicxml", "mid"):
        raise HTTPException(400, "fmt must be 'musicxml' or 'mid'")
    project = load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    path = project.export_path(fmt)
    if not path.exists():
        raise HTTPException(404, "not exported yet -- call /export first")
    media_type = "application/vnd.recordare.musicxml+xml" if fmt == "musicxml" else "audio/midi"
    return FileResponse(path, media_type=media_type, filename=f"score.{fmt}")
