"""Pydantic request/response models for the API layer."""

from __future__ import annotations

from pydantic import BaseModel


class IngestUrlRequest(BaseModel):
    url: str


class ProjectSummary(BaseModel):
    project_id: str
    source_label: str
    created_at: float
    stages: dict[str, bool]
    active_stem: str | None = None


class NoteOut(BaseModel):
    id: str | None
    pitch_midi: int
    onset_s: float
    offset_s: float
    confidence: float
    beat: float | None = None
    duration_beats: float | None = None
    written_pitch_midi: int | None = None
    folded: bool = False
    folded_octaves: int = 0
    deleted: bool = False


class TranscribeRequest(BaseModel):
    stem: str | None = None  # None = full mix
    onset_threshold: float | None = None
    frame_threshold: float | None = None
    minimum_note_length_ms: float | None = None


class AnalysisOut(BaseModel):
    bpm: float
    key_tonic: str
    key_mode: str
    key_sharps: int


class QuantizeSettingsIn(BaseModel):
    bpm: float = 120.0
    grid: str = "16th"
    swing: float = 0.0
    time_signature: str = "4/4"


class ScoreSettingsIn(BaseModel):
    instrument: str = "alto"  # soprano | alto | tenor | baritone
    global_octave_shift: int = 0
    quantize: QuantizeSettingsIn = QuantizeSettingsIn()


class ScoreNoteOut(NoteOut):
    pass


class ScoreOut(BaseModel):
    notes: list[ScoreNoteOut]
    key_sharps: int  # written key signature for the chosen instrument


class ScoreModelOut(BaseModel):
    key_sharps: int
    time_signature: str
    bpm: float
    notes: list[dict]


class ExportOut(BaseModel):
    score_model: ScoreModelOut
    musicxml_url: str
    midi_url: str
