// Sampled saxophone preview (Soundfont-player, FluidR3_GM sax patches).
// Plays either the written (transposed, per-instrument) line or the raw
// concert-pitch transcription, selected by the caller via `pitchField`.
const GM_SAX_NAME = {
  soprano: "soprano_sax",
  alto: "alto_sax",
  tenor: "tenor_sax",
  baritone: "baritone_sax",
};

class SaxPlayer {
  constructor() {
    this.ctx = null;
    this._instruments = {}; // name -> loaded Soundfont instrument
    this._loading = {};
  }

  async _ensureLoaded(name) {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this._instruments[name]) return this._instruments[name];
    if (this._loading[name]) return this._loading[name];
    this._loading[name] = Soundfont.instrument(this.ctx, name).then((inst) => {
      this._instruments[name] = inst;
      return inst;
    });
    return this._loading[name];
  }

  /**
   * @param {Array} notes - NoteEvent-shaped objects.
   * @param {Object} opts
   * @param {string} opts.instrument - one of soprano|alto|tenor|baritone
   * @param {"written"|"concert"} opts.pitchField - which pitch to play
   */
  async playNotes(notes, { instrument = "alto", pitchField = "written" } = {}) {
    const gmName = GM_SAX_NAME[instrument] || "alto_sax";
    const inst = await this._ensureLoaded(gmName);
    this.stop();
    const startAt = this.ctx.currentTime + 0.15;
    for (const n of notes) {
      if (n.deleted) continue;
      const pitch = pitchField === "concert" ? n.pitch_midi : (n.written_pitch_midi ?? n.pitch_midi);
      const duration = Math.max(0.08, n.offset_s - n.onset_s);
      inst.play(pitch, startAt + n.onset_s, { duration, gain: Math.max(0.3, Math.min(1, n.confidence)) });
    }
  }

  stop() {
    for (const inst of Object.values(this._instruments)) {
      if (inst.stop) inst.stop();
    }
  }
}

const saxPlayer = new SaxPlayer();
