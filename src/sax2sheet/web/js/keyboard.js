// A drawn piano keyboard strip. Exposes the exact key x-position geometry
// that fallingnotes.js uses to align falling notes with physical keys, so
// there's exactly one place (here) that knows how MIDI pitch maps to
// horizontal position -- the falling notes and the keyboard can never drift
// out of alignment with each other.
//
// Layout uses the standard continuous piano-key geometry: within an octave,
// each pitch class gets a fractional "white-key-width" offset (black keys
// sit between their neighboring white keys, not on a separate grid).

const PC_OFFSET = { 0: 0, 1: 0.65, 2: 1, 3: 1.75, 4: 2, 5: 3, 6: 3.6, 7: 4, 8: 4.7, 9: 5, 10: 5.8, 11: 6 };
const BLACK_PCS = new Set([1, 3, 6, 8, 10]);

function isBlackKey(midi) {
  return BLACK_PCS.has(((midi % 12) + 12) % 12);
}

/** Continuous x position in units of "one white key width", NOT pixels. */
function pianoKeySlot(midi) {
  const octave = Math.floor(midi / 12);
  const pc = ((midi % 12) + 12) % 12;
  return octave * 7 + PC_OFFSET[pc];
}

class PianoKeyboard {
  constructor(container, { minMidi = 48, maxMidi = 84 } = {}) {
    this.container = container;
    this.minMidi = minMidi;
    this.maxMidi = maxMidi;
    this.height = 90;
    this.litKeys = new Map(); // midi -> css color

    this.canvas = document.createElement("canvas");
    container.innerHTML = "";
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    this._layout();
    this._resizeHandler = () => { this._layout(); this.draw(); };
    window.addEventListener("resize", this._resizeHandler);
  }

  setRange(minMidi, maxMidi) {
    this.minMidi = minMidi;
    this.maxMidi = maxMidi;
    this._layout();
  }

  _layout() {
    const dpr = window.devicePixelRatio || 1;
    this.width = this.container.clientWidth || 800;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.canvas.style.width = this.width + "px";
    this.canvas.style.height = this.height + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const minSlot = pianoKeySlot(this.minMidi);
    const maxSlot = pianoKeySlot(this.maxMidi) + 1; // +1 so the last key has room
    this.whiteKeyWidth = this.width / (maxSlot - minSlot);
    this._originPx = -minSlot * this.whiteKeyWidth;
  }

  /** Pixel x for the left edge of a white key, or the visual center for a black key. */
  xForMidi(midi) {
    return this._originPx + pianoKeySlot(midi) * this.whiteKeyWidth;
  }

  setLit(midi, color) {
    if (color) this.litKeys.set(midi, color);
    else this.litKeys.delete(midi);
  }

  clearLit() {
    this.litKeys.clear();
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    for (let m = this.minMidi; m <= this.maxMidi; m++) {
      if (isBlackKey(m)) continue;
      const x = this.xForMidi(m);
      ctx.fillStyle = this.litKeys.get(m) || "#fdfdfd";
      ctx.strokeStyle = "#555";
      ctx.lineWidth = 1;
      ctx.fillRect(x, 0, this.whiteKeyWidth - 1, this.height);
      ctx.strokeRect(x, 0, this.whiteKeyWidth - 1, this.height);
    }

    const blackWidth = this.whiteKeyWidth * 0.6;
    const blackHeight = this.height * 0.62;
    for (let m = this.minMidi; m <= this.maxMidi; m++) {
      if (!isBlackKey(m)) continue;
      const x = this.xForMidi(m) - blackWidth / 2;
      ctx.fillStyle = this.litKeys.get(m) || "#1a1a1a";
      ctx.fillRect(x, 0, blackWidth, blackHeight);
    }
  }

  destroy() {
    window.removeEventListener("resize", this._resizeHandler);
  }
}
