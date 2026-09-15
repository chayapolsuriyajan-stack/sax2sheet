// A real-time beat clock driving the falling-notes/keyboard visualization
// (and, in a later workstream, audio scheduling and wait-mode). This is
// what makes pause/seek/tempo-change actually work: currentBeat() is always
// derived fresh from wall-clock time against an anchor point, rather than
// anything being scheduled upfront the way playback.js's preview buttons
// work -- there's nothing to "cancel" when you pause or change tempo, only
// the anchor needs updating.

class Transport {
  constructor(bpm = 120) {
    this.bpm = bpm;
    this.tempoScale = 1.0;
    this.playing = false;
    this._anchorWallMs = 0;
    this._anchorBeat = 0;
    this._onTick = null;
    this._rafId = null;
  }

  currentBeat() {
    if (!this.playing) return this._anchorBeat;
    const elapsedSec = (performance.now() - this._anchorWallMs) / 1000;
    const beatsPerSec = (this.bpm * this.tempoScale) / 60;
    return this._anchorBeat + elapsedSec * beatsPerSec;
  }

  play() {
    if (this.playing) return;
    this._anchorBeat = this.currentBeat();
    this._anchorWallMs = performance.now();
    this.playing = true;
    this._loop();
  }

  pause() {
    if (!this.playing) return;
    this._anchorBeat = this.currentBeat();
    this.playing = false;
    if (this._rafId) cancelAnimationFrame(this._rafId);
  }

  seek(beat) {
    this._anchorBeat = Math.max(0, beat);
    this._anchorWallMs = performance.now();
  }

  setTempoScale(scale) {
    // Re-anchor first so the new scale takes effect from *now*, not from
    // the original t=0 -- otherwise the beat position would jump.
    this._anchorBeat = this.currentBeat();
    this._anchorWallMs = performance.now();
    this.tempoScale = scale;
  }

  /** fn(currentBeat) is called once per animation frame while playing, and
   * once immediately on any state change (play/pause/seek) so a paused
   * transport still reflects its position on screen.
   */
  onTick(fn) {
    this._onTick = fn;
  }

  _loop() {
    if (this._onTick) this._onTick(this.currentBeat());
    if (!this.playing) return;
    this._rafId = requestAnimationFrame(() => this._loop());
  }

  /** Forces one render at the current position without starting playback --
   * use after setNotes()/seek() while paused so the view updates.
   */
  tickOnce() {
    if (this._onTick) this._onTick(this.currentBeat());
  }
}
