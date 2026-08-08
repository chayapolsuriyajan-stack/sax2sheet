// Sampled instrument preview (Soundfont-player, FluidR3_GM patches).
// Plays either the written (transposed, per-instrument) line or the raw
// concert-pitch transcription, selected by the caller via `pitchField`.
//
// Sample data is loaded from local vendored files (web/vendor/soundfonts/),
// not the Soundfont-player default CDN -- this is a *local* tool and
// shouldn't need live internet access to play back a preview, and a slow or
// blocked CDN would otherwise fail silently (playback just doesn't happen,
// with no visible error).
const GM_INSTRUMENT_NAME = {
  soprano: "soprano_sax",
  alto: "alto_sax",
  tenor: "tenor_sax",
  baritone: "baritone_sax",
  guitar: "acoustic_guitar_nylon",
  piano: "acoustic_grand_piano",
};

function localSoundfontUrl(name) {
  return `/vendor/soundfonts/${name}-mp3.js`;
}

class SaxPlayer {
  constructor() {
    this.ctx = null;
    this._instruments = {}; // name -> loaded Soundfont instrument
    this._loading = {};
  }

  async _ensureLoaded(name) {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    // Browsers may create a fresh AudioContext in a "suspended" state even
    // inside a click handler; resume() is a no-op if it's already running.
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }
    if (this._instruments[name]) return this._instruments[name];
    if (this._loading[name]) return this._loading[name];
    this._loading[name] = Soundfont.instrument(this.ctx, name, { nameToUrl: localSoundfontUrl })
      .then((inst) => {
        this._instruments[name] = inst;
        return inst;
      })
      .catch((err) => {
        delete this._loading[name];
        throw new Error(`Failed to load ${name} sample set: ${err.message || err}`);
      });
    return this._loading[name];
  }

  /**
   * @param {Array} notes - NoteEvent-shaped objects.
   * @param {Object} opts
   * @param {string} opts.instrument - one of soprano|alto|tenor|baritone|guitar|piano
   * @param {"written"|"concert"} opts.pitchField - which pitch to play
   */
  async playNotes(notes, { instrument = "alto", pitchField = "written" } = {}) {
    const gmName = GM_INSTRUMENT_NAME[instrument] || "alto_sax";
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

  /**
   * Plays a plain oscillator beep -- zero network/soundfont dependency.
   * Diagnostic aid: if this is silent, the problem is the browser's audio
   * output (muted tab, wrong output device, OS volume), not soundfont
   * loading. If this works but instrument playback doesn't, the problem is
   * specific to sample loading -- check the console for the failed URL.
   */
  async testTone() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.frequency.value = 440;
    gain.gain.value = 0.2;
    osc.connect(gain).connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.4);
  }
}

const saxPlayer = new SaxPlayer();
