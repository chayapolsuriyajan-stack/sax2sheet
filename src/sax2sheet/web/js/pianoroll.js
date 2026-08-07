// Canvas piano roll with light editing, per the plan:
//   click            -> select (shift/ctrl-click to multi-select)
//   Delete/Backspace -> delete selected notes
//   drag note body   -> move (pitch + onset, duration preserved)
//   drag note edge   -> resize (change duration)
//   drag empty area  -> box-select
//   confidence slider -> visual filter (dim notes below threshold)
//
// Edits are non-destructive: every mutation calls `onEdit(op)`, which the
// caller persists as an operation appended to notes.edits.json and returns
// the recomputed current note list. This module never has its own notion of
// "truth" -- it just renders whatever note list it's given.

const EDGE_GRAB_PX = 6;
const TIME_SNAP_S = 0.05; // placeholder grid until quantize.py lands (Phase 3)

class PianoRoll {
  constructor(container, { onEdit, onSelectionChange, readOnly = false } = {}) {
    this.container = container;
    this.onEdit = onEdit || (async () => {});
    this.onSelectionChange = onSelectionChange || (() => {});
    this.readOnly = readOnly;
    this.notes = [];
    this.selected = new Set();
    this.confidenceThreshold = 0;
    this.drag = null; // { mode: 'move'|'resize'|'box', ... }

    this.canvas = document.createElement("canvas");
    this.canvas.tabIndex = 0; // so it can receive keydown
    container.innerHTML = "";
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    this._bindEvents();
  }

  setNotes(notes) {
    this.notes = notes;
    this.selected = new Set([...this.selected].filter((id) => notes.some((n) => n.id === id)));
    this._layout();
    this._draw();
  }

  setConfidenceThreshold(v) {
    this.confidenceThreshold = v;
    this._draw();
  }

  getSelectedIds() {
    return [...this.selected];
  }

  // -- coordinate mapping -------------------------------------------------
  _layout() {
    const visible = this.notes.filter((n) => !n.deleted);
    const dpr = window.devicePixelRatio || 1;
    this.width = this.container.clientWidth || 860;
    this.height = 340;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.canvas.style.width = this.width + "px";
    this.canvas.style.height = this.height + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this.maxT = visible.length ? Math.max(...visible.map((n) => n.offset_s)) : 1;
    const pitches = visible.length ? visible.map((n) => n.pitch_midi) : [60];
    this.minPitch = Math.min(...pitches) - 2;
    this.maxPitch = Math.max(...pitches) + 2;
  }

  xForT(t) {
    return (t / (this.maxT || 1)) * (this.width - 20) + 10;
  }
  tForX(x) {
    return Math.max(0, ((x - 10) / (this.width - 20)) * (this.maxT || 1));
  }
  yForPitch(p) {
    const span = this.maxPitch - this.minPitch || 1;
    return this.height - 10 - ((p - this.minPitch) / span) * (this.height - 20);
  }
  pitchForY(y) {
    const span = this.maxPitch - this.minPitch || 1;
    const p = this.minPitch + ((this.height - 10 - y) / (this.height - 20)) * span;
    return Math.round(p);
  }
  snapTime(t) {
    return Math.max(0, Math.round(t / TIME_SNAP_S) * TIME_SNAP_S);
  }

  // -- drawing --------------------------------------------------------------
  _draw() {
    const ctx = this.ctx;
    ctx.fillStyle = "#101216";
    ctx.fillRect(0, 0, this.width, this.height);

    ctx.strokeStyle = "#2c3038";
    ctx.lineWidth = 1;
    for (let p = Math.ceil(this.minPitch / 12) * 12; p <= this.maxPitch; p += 12) {
      const y = this.yForPitch(p);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
    }

    for (const note of this.notes) {
      if (note.deleted) continue;
      const x1 = this.xForT(note.onset_s);
      const x2 = this.xForT(note.offset_s);
      const y = this.yForPitch(note.pitch_midi);
      const dim = note.confidence < this.confidenceThreshold;
      const selected = this.selected.has(note.id);

      const alpha = dim ? 0.15 : Math.max(0.35, Math.min(1, note.confidence));
      ctx.fillStyle = note.folded
        ? `rgba(230, 160, 50, ${alpha})` // amber for octave-folded notes (Phase 3)
        : `rgba(232, 163, 61, ${alpha})`;
      ctx.fillRect(x1, y - 4, Math.max(2, x2 - x1), 8);

      if (selected) {
        ctx.strokeStyle = "#5bc0ff";
        ctx.lineWidth = 2;
        ctx.strokeRect(x1 - 1, y - 5, Math.max(2, x2 - x1) + 2, 10);
      }
    }

    if (this.drag && this.drag.mode === "box") {
      const { x0, y0, x1, y1 } = this.drag;
      ctx.strokeStyle = "#5bc0ff";
      ctx.fillStyle = "rgba(91,192,255,0.12)";
      const rx = Math.min(x0, x1), ry = Math.min(y0, y1);
      const rw = Math.abs(x1 - x0), rh = Math.abs(y1 - y0);
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeRect(rx, ry, rw, rh);
    }
  }

  // -- hit testing ------------------------------------------------------
  _noteAt(x, y) {
    for (let i = this.notes.length - 1; i >= 0; i--) {
      const n = this.notes[i];
      if (n.deleted) continue;
      const x1 = this.xForT(n.onset_s);
      const x2 = this.xForT(n.offset_s);
      const cy = this.yForPitch(n.pitch_midi);
      if (x >= x1 - 2 && x <= x2 + 2 && Math.abs(y - cy) <= 6) {
        const edge = x >= x2 - EDGE_GRAB_PX;
        return { note: n, edge };
      }
    }
    return null;
  }

  // -- events -------------------------------------------------------------
  _bindEvents() {
    this.canvas.addEventListener("mousedown", (e) => this._onMouseDown(e));
    window.addEventListener("mousemove", (e) => this._onMouseMove(e));
    window.addEventListener("mouseup", (e) => this._onMouseUp(e));
    this.canvas.addEventListener("keydown", (e) => this._onKeyDown(e));
    window.addEventListener("resize", () => { this._layout(); this._draw(); });
  }

  _localXY(e) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  _onMouseDown(e) {
    if (this.readOnly) return;
    this.canvas.focus();
    const { x, y } = this._localXY(e);
    const hit = this._noteAt(x, y);

    if (hit) {
      const multi = e.shiftKey || e.ctrlKey || e.metaKey;
      if (!this.selected.has(hit.note.id)) {
        if (!multi) this.selected.clear();
        this.selected.add(hit.note.id);
      } else if (multi) {
        this.selected.delete(hit.note.id);
      }
      this.onSelectionChange([...this.selected]);

      this.drag = {
        mode: hit.edge ? "resize" : "move",
        id: hit.note.id,
        startX: x,
        startY: y,
        origOnset: hit.note.onset_s,
        origOffset: hit.note.offset_s,
        origPitch: hit.note.pitch_midi,
      };
    } else {
      if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
        this.selected.clear();
        this.onSelectionChange([]);
      }
      this.drag = { mode: "box", x0: x, y0: y, x1: x, y1: y };
    }
    this._draw();
  }

  _onMouseMove(e) {
    if (!this.drag) return;
    const { x, y } = this._localXY(e);

    if (this.drag.mode === "box") {
      this.drag.x1 = x;
      this.drag.y1 = y;
      this._draw();
      return;
    }

    const note = this.notes.find((n) => n.id === this.drag.id);
    if (!note) return;

    if (this.drag.mode === "move") {
      const dt = this.tForX(x) - this.tForX(this.drag.startX);
      const dur = this.drag.origOffset - this.drag.origOnset;
      note.onset_s = Math.max(0, this.drag.origOnset + dt);
      note.offset_s = note.onset_s + dur;
      note.pitch_midi = this.pitchForY(y - (this.yForPitch(this.drag.origPitch) - this.drag.startY));
    } else if (this.drag.mode === "resize") {
      const newOffset = Math.max(note.onset_s + 0.03, this.tForX(x));
      note.offset_s = newOffset;
    }
    this._draw();
  }

  async _onMouseUp(e) {
    if (!this.drag) return;
    const drag = this.drag;
    this.drag = null;

    if (drag.mode === "box") {
      const rx = Math.min(drag.x0, drag.x1), ry = Math.min(drag.y0, drag.y1);
      const rw = Math.abs(drag.x1 - drag.x0), rh = Math.abs(drag.y1 - drag.y0);
      if (rw > 3 || rh > 3) {
        for (const n of this.notes) {
          if (n.deleted) continue;
          const x1 = this.xForT(n.onset_s), x2 = this.xForT(n.offset_s);
          const cy = this.yForPitch(n.pitch_midi);
          if (x2 >= rx && x1 <= rx + rw && cy >= ry && cy <= ry + rh) {
            this.selected.add(n.id);
          }
        }
        this.onSelectionChange([...this.selected]);
      }
      this._draw();
      return;
    }

    const note = this.notes.find((n) => n.id === drag.id);
    if (!note) return;

    if (drag.mode === "move") {
      const onset = this.snapTime(note.onset_s);
      const offset = onset + (drag.origOffset - drag.origOnset);
      await this.onEdit({ op: "set_time", ids: [drag.id], onset_s: onset, offset_s: offset });
      if (note.pitch_midi !== drag.origPitch) {
        await this.onEdit({ op: "set_pitch", ids: [drag.id], pitch_midi: note.pitch_midi });
      }
    } else if (drag.mode === "resize") {
      const offset = this.snapTime(note.offset_s);
      await this.onEdit({ op: "set_time", ids: [drag.id], offset_s: Math.max(note.onset_s + 0.03, offset) });
    }
  }

  async _onKeyDown(e) {
    if ((e.key === "Delete" || e.key === "Backspace") && this.selected.size) {
      e.preventDefault();
      await this.onEdit({ op: "delete", ids: [...this.selected] });
      this.selected.clear();
      this.onSelectionChange([]);
    }
  }

  async shiftSelectionOctave(direction) {
    if (!this.selected.size) return;
    await this.onEdit({ op: "shift_octave", ids: [...this.selected], semitones: 12 * direction });
  }

  async deleteSelection() {
    if (!this.selected.size) return;
    await this.onEdit({ op: "delete", ids: [...this.selected] });
    this.selected.clear();
    this.onSelectionChange([]);
  }
}
