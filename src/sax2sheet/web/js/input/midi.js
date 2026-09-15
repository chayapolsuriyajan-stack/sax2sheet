// Web MIDI input: exact pitch, velocity and timing, no ambiguity -- the
// accurate path whenever a MIDI keyboard is available (see plan). Falls
// back silently when the browser doesn't support Web MIDI, the user
// declines the permission prompt, or no input device is actually plugged
// in -- callers check hasDevice() and fall back to MicInput (mic.js).

class MidiInput {
  constructor() {
    this.access = null;
    this.heldNotes = new Set();
    this._noteOnHandlers = [];
    this._noteOffHandlers = [];
  }

  static isSupported() {
    return typeof navigator !== "undefined" && !!navigator.requestMIDIAccess;
  }

  /** @returns {Promise<boolean>} whether MIDI access was granted (not
   * whether a device is present -- check hasDevice() for that).
   */
  async start() {
    if (!MidiInput.isSupported()) return false;
    try {
      this.access = await navigator.requestMIDIAccess();
    } catch (e) {
      console.warn("MIDI access denied or unavailable", e);
      return false;
    }
    this._attachToInputs();
    this.access.onstatechange = () => this._attachToInputs();
    return true;
  }

  _attachToInputs() {
    for (const input of this.access.inputs.values()) {
      input.onmidimessage = (msg) => this._handleMessage(msg);
    }
  }

  _handleMessage(msg) {
    const [status, note, velocity] = msg.data;
    const command = status & 0xf0;
    if (command === 0x90 && velocity > 0) {
      this.heldNotes.add(note);
      this._noteOnHandlers.forEach((fn) => fn(note, velocity));
    } else if (command === 0x80 || (command === 0x90 && velocity === 0)) {
      this.heldNotes.delete(note);
      this._noteOffHandlers.forEach((fn) => fn(note));
    }
  }

  onNoteOn(fn) {
    this._noteOnHandlers.push(fn);
  }

  onNoteOff(fn) {
    this._noteOffHandlers.push(fn);
  }

  getHeldNotes() {
    return new Set(this.heldNotes);
  }

  hasDevice() {
    return !!(this.access && this.access.inputs.size > 0);
  }

  stop() {
    if (this.access) {
      for (const input of this.access.inputs.values()) input.onmidimessage = null;
      this.access.onstatechange = null;
    }
    this.heldNotes.clear();
  }
}
