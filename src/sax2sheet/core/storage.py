"""File-based project storage.

Each project lives at `data/projects/<id>/`, where `<id>` is the sha1 of the
normalized source audio. Re-ingesting the same audio resolves to the same
folder, so cached stems and prior transcriptions are reused automatically.

Layout (see plan for full rationale):
    manifest.json       source metadata, settings, stage status
    source.wav          normalized audio
    stems/               vocals.wav other.wav bass.wav drums.wav (cached)
    notes.raw.json       Basic Pitch output -- written once, never mutated
    notes.edits.json     manual corrections, replayed on load
    analysis.json        tempo, beats, key
    exports/              score.pdf score.musicxml score.mid
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sax2sheet.config import settings


def hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


@dataclass(slots=True)
class Manifest:
    project_id: str
    source_label: str  # original filename or URL, for display
    created_at: float = field(default_factory=time.time)
    stages: dict[str, bool] = field(
        default_factory=lambda: {
            "ingested": False,
            "separated": False,
            "transcribed": False,
            "analyzed": False,
        }
    )
    active_stem: str | None = None  # None = full mix

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        data = json.loads(text)
        return cls(**data)


class Project:
    """Handle to a single project folder. Does not itself run any pipeline
    stage -- other core modules read/write files through this handle.
    """

    def __init__(self, project_id: str):
        self.id = project_id
        self.dir = settings.projects_dir / project_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "stems").mkdir(exist_ok=True)
        (self.dir / "exports").mkdir(exist_ok=True)

    # -- manifest --------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.json"

    def load_manifest(self) -> Manifest | None:
        if not self.manifest_path.exists():
            return None
        return Manifest.from_json(self.manifest_path.read_text())

    def save_manifest(self, manifest: Manifest) -> None:
        self.manifest_path.write_text(manifest.to_json())

    # -- well-known file paths -------------------------------------------
    @property
    def source_wav(self) -> Path:
        return self.dir / "source.wav"

    def stem_wav(self, stem: str) -> Path:
        return self.dir / "stems" / f"{stem}.wav"

    @property
    def notes_raw_json(self) -> Path:
        return self.dir / "notes.raw.json"

    @property
    def notes_edits_json(self) -> Path:
        return self.dir / "notes.edits.json"

    @property
    def analysis_json(self) -> Path:
        return self.dir / "analysis.json"

    def export_path(self, ext: str) -> Path:
        return self.dir / "exports" / f"score.{ext}"


def get_or_create_project(source_wav: Path, source_label: str) -> Project:
    """Resolve a normalized source WAV to its project folder, creating a new
    one (and writing the manifest) if this audio hasn't been seen before.
    """
    project_id = hash_file(source_wav)
    project = Project(project_id)
    if project.manifest_path.exists():
        return project

    # New project: move the normalized audio into place and write manifest.
    if source_wav.resolve() != project.source_wav.resolve():
        project.source_wav.write_bytes(source_wav.read_bytes())
    manifest = Manifest(project_id=project_id, source_label=source_label)
    manifest.stages["ingested"] = True
    project.save_manifest(manifest)
    return project


def load_project(project_id: str) -> Project | None:
    project = Project(project_id)
    if not project.manifest_path.exists():
        return None
    return project


def list_projects() -> list[Manifest]:
    out = []
    for d in settings.projects_dir.iterdir():
        if not d.is_dir():
            continue
        p = Project(d.name)
        m = p.load_manifest()
        if m:
            out.append(m)
    return sorted(out, key=lambda m: m.created_at, reverse=True)
