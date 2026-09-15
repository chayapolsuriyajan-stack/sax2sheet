// Falling-notes visualization (Synthesia-style): notes descend toward the
// piano keyboard as the transport plays, colored by hand, and "get absorbed"
// into the keyboard as they're played rather than just vanishing at a line.
// Horizontal position comes directly from the PianoKeyboard instance (see
// keyboard.js) so the notes and the physical keys can never drift out of
// alignment with each other.

const HAND_COLORS = { R: "#5bc0ff", L: "#e8a33d" };
const DEFAULT_COLOR = "#8fd15c"; // hand unknown/not applicable (single-staff instrument)

class FallingNotes {
  constructor(container, keyboard, { pixelsPerBeat = 70, lookaheadBeats = 6 } = {}) {
    this.container = container;
    this.keyboard = keyboard;
    this.pixelsPerBeat = pixelsPerBeat;
    this.lookaheadBeats = lookaheadBeats;
    this.notes = [];
    this.height = 320;

    this.canvas = document.createElement("canvas");
    container.innerHTML = "";
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    this._layout();
    this._resizeHandler = () => this._layout();
    window.addEventListener("resize", this._resizeHandler);
  }

  _layout() {
    const dpr = window.devicePixelRatio || 1;
    this.width = this.container.clientWidth || 800;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.canvas.style.width = this.width + "px";
    this.canvas.style.height = this.height + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /** notes: [{beat, duration_beats, written_pitch_midi, hand, finger}, ...] */
  setNotes(notes) {
    this.notes = notes;
  }

  /** Redraws for the given transport position (in beats) and lights the
   * keyboard keys currently sounding. Call this every animation frame.
   */
  render(currentBeat) {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    // Guideline grid: a faint horizontal line at the hit point.
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.beginPath();
    ctx.moveTo(0, this.height - 1);
    ctx.lineTo(this.width, this.height - 1);
    ctx.stroke();

    this.keyboard.clearLit();

    for (const n of this.notes) {
      const noteEnd = n.beat + n.duration_beats;
      if (noteEnd < currentBeat) continue;
      if (n.beat > currentBeat + this.lookaheadBeats) continue;

      // The bottom of the note stays pinned at the hit line while playing
      // (max(0, ...) clamps it there instead of continuing past); the top
      // shrinks toward the line as the note is consumed -- the note visibly
      // "gets absorbed" into the keyboard rather than just disappearing.
      const yBottom = this.height - Math.max(0, n.beat - currentBeat) * this.pixelsPerBeat;
      const yTop = this.height - Math.max(0, noteEnd - currentBeat) * this.pixelsPerBeat;

      const midi = n.written_pitch_midi;
      const black = isBlackKey(midi);
      const keyWidth = black ? this.keyboard.whiteKeyWidth * 0.6 : this.keyboard.whiteKeyWidth - 1;
      const x = black ? this.keyboard.xForMidi(midi) - keyWidth / 2 : this.keyboard.xForMidi(midi);
      const color = HAND_COLORS[n.hand] || DEFAULT_COLOR;

      ctx.fillStyle = color;
      const h = Math.max(3, yBottom - yTop);
      ctx.fillRect(x + 1, yTop, Math.max(2, keyWidth - 2), h);

      if (n.finger) {
        ctx.fillStyle = "#101216";
        ctx.font = "bold 11px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(String(n.finger), x + keyWidth / 2, yTop + 13);
      }

      if (n.beat <= currentBeat && currentBeat < noteEnd) {
        this.keyboard.setLit(midi, color);
      }
    }

    this.keyboard.draw();
  }

  destroy() {
    window.removeEventListener("resize", this._resizeHandler);
  }
}
