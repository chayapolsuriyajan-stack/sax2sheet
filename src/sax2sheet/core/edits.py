"""Piano-roll manual edits, stored as a non-destructive operation log layered
on top of notes.raw.json.

Editing never mutates the raw transcription; each user action (delete, move a
note, bulk octave-shift a selection) is appended as an EditOp and replayed
over the raw notes on load. This mirrors the same non-destructive shape as
quantization and transposition: expensive/authoritative data stays untouched,
cheap correction layers sit on top and can be recomputed instantly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sax2sheet.core.models import NoteEvent

VALID_OPS = {"delete", "restore", "set_pitch", "set_time", "shift_octave"}


@dataclass(slots=True)
class EditOp:
    op: str  # one of VALID_OPS
    ids: list[str] = field(default_factory=list)
    pitch_midi: int | None = None
    onset_s: float | None = None
    offset_s: float | None = None
    semitones: int | None = None

    def __post_init__(self):
        if self.op not in VALID_OPS:
            raise ValueError(f"unknown edit op: {self.op!r}")


def load_edits(path: Path) -> list[EditOp]:
    if not path.exists():
        return []
    return [EditOp(**e) for e in json.loads(path.read_text())]


def save_edits(path: Path, edits: list[EditOp]) -> None:
    path.write_text(json.dumps([asdict(e) for e in edits], indent=2))


def append_edit(path: Path, edit: EditOp) -> list[EditOp]:
    edits = load_edits(path)
    edits.append(edit)
    save_edits(path, edits)
    return edits


def undo_last(path: Path) -> list[EditOp]:
    edits = load_edits(path)
    if edits:
        edits.pop()
    save_edits(path, edits)
    return edits


def clear_edits(path: Path) -> None:
    save_edits(path, [])


def apply_edits(raw_notes: list[NoteEvent], edits: list[EditOp]) -> list[NoteEvent]:
    """Replay the operation log over raw notes. Pure function -- raw_notes is
    never mutated, and calling this repeatedly with the same inputs always
    produces the same output.
    """
    by_id: dict[str, NoteEvent] = {n.id: NoteEvent(**asdict(n)) for n in raw_notes}
    order = [n.id for n in raw_notes]

    for edit in edits:
        for nid in edit.ids:
            note = by_id.get(nid)
            if note is None:
                continue
            if edit.op == "delete":
                note.deleted = True
            elif edit.op == "restore":
                note.deleted = False
            elif edit.op == "set_pitch" and edit.pitch_midi is not None:
                note.pitch_midi = edit.pitch_midi
            elif edit.op == "set_time":
                if edit.onset_s is not None:
                    note.onset_s = edit.onset_s
                if edit.offset_s is not None:
                    note.offset_s = edit.offset_s
            elif edit.op == "shift_octave" and edit.semitones is not None:
                note.pitch_midi += edit.semitones

    return [by_id[nid] for nid in order if nid in by_id]
