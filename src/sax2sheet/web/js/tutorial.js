// Orchestrates the play-along tutorial's "wait mode": holds playback at the
// next unplayed note(s) until the expected pitch(es) are actually detected
// as being played, then advances -- see plan. Auto-prefers MIDI (exact, no
// ambiguity) over mic (approximate) when both are available; falls back to
// mic-only when no MIDI device is present.
//
// Notes sharing a beat are grouped into one "chord" that must ALL be
// satisfied together before advancing -- this is what makes a piano LH
// chord require every note, not just one of them.

class TutorialController {
  constructor(transport, notes) {
    this.transport = transport;
    this.waitMode = false;
    this.midi = null;
    this.mic = null;
    this.activeInput = null; // "midi" | "mic" | null
    this.onStatus = null; // caller-supplied ({beat, expected, satisfied, groupIndex, total}) => void
    this.onWaitModeChange = null; // caller-supplied (enabled) => void -- fires on BOTH
    // user-triggered setWaitMode() calls and the internal auto-off when the
    // piece completes, so the UI (checkbox, Play/Pause buttons) can stay in
    // sync even when wait mode turns itself off without the checkbox being
    // clicked.
    this._pollTimer = null;
    this._currentGroupIndex = 0;
    this.setNotes(notes);
  }

  setNotes(notes) {
    this._groups = this._groupNotesByBeat(notes.filter((n) => !n.deleted));
    this._currentGroupIndex = 0;
  }

  _groupNotesByBeat(notes) {
    const byBeat = new Map();
    for (const n of notes) {
      if (!byBeat.has(n.beat)) byBeat.set(n.beat, []);
      byBeat.get(n.beat).push(n);
    }
    return [...byBeat.entries()].sort((a, b) => a[0] - b[0]).map(([beat, group]) => ({ beat, group }));
  }

  /** Requests MIDI first (falls back to mic if no MIDI device responds),
   * asking for user permission along the way -- must be called from a
   * user-gesture handler (a button click), not automatically.
   * @returns {Promise<"midi"|"mic"|null>} which input ended up active.
   */
  async ensureInput() {
    if (this.activeInput) return this.activeInput;

    this.midi = new MidiInput();
    const midiGranted = await this.midi.start().catch(() => false);
    if (midiGranted && this.midi.hasDevice()) {
      this.activeInput = "midi";
      return "midi";
    }

    this.mic = new MicInput();
    try {
      await this.mic.start();
      this.activeInput = "mic";
      return "mic";
    } catch (e) {
      console.warn("Microphone access failed", e);
      return null;
    }
  }

  setWaitMode(enabled) {
    this.waitMode = enabled;
    if (enabled) {
      this._currentGroupIndex = this._groupIndexForBeat(this.transport.currentBeat());
      this.transport.pause();
      this._startPolling();
    } else {
      this._stopPolling();
    }
    if (this.onWaitModeChange) this.onWaitModeChange(enabled);
  }

  _groupIndexForBeat(beat) {
    let idx = 0;
    while (idx < this._groups.length - 1 && this._groups[idx].beat < beat - 0.01) idx++;
    return idx;
  }

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => this._checkCurrentGroup(), 80);
    this._checkCurrentGroup();
  }

  _stopPolling() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    this._pollTimer = null;
  }

  _checkCurrentGroup() {
    if (this._currentGroupIndex >= this._groups.length) {
      this.setWaitMode(false);
      return;
    }
    const { beat, group } = this._groups[this._currentGroupIndex];
    const expected = group.map((n) => n.written_pitch_midi);
    const satisfied = this._checkSatisfied(expected);

    if (this.onStatus) {
      this.onStatus({ beat, expected, satisfied, groupIndex: this._currentGroupIndex, total: this._groups.length });
    }

    if (satisfied) this._advance();
  }

  _checkSatisfied(expected) {
    if (this.activeInput === "midi") {
      const held = this.midi.getHeldNotes();
      return expected.every((m) => held.has(m));
    }
    if (this.activeInput === "mic") {
      if (expected.length === 1) {
        const detected = this.mic.detectMonophonicPitch();
        return !!detected && detected.clarity > 0.5 && Math.abs(detected.midi - expected[0]) < 0.5;
      }
      const sounding = this.mic.verifyExpectedPitches(expected);
      return expected.every((m) => sounding.has(m));
    }
    return false;
  }

  _advance() {
    this._currentGroupIndex++;
    if (this._currentGroupIndex >= this._groups.length) {
      const lastBeat = this._groups[this._groups.length - 1].beat;
      this.setWaitMode(false);
      this.transport.seek(lastBeat);
      this.transport.tickOnce();
      return;
    }
    const nextBeat = this._groups[this._currentGroupIndex].beat;
    this.transport.seek(nextBeat);
    this.transport.tickOnce();
  }

  stop() {
    this._stopPolling();
    if (this.midi) this.midi.stop();
    if (this.mic) this.mic.stop();
    this.activeInput = null;
    this.midi = null;
    this.mic = null;
  }
}
