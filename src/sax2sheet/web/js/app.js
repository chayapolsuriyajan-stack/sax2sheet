const fileInput = document.getElementById("file-input");
const urlInput = document.getElementById("url-input");
const urlSubmit = document.getElementById("url-submit");
const ingestStatus = document.getElementById("ingest-status");

const transcribePanel = document.getElementById("transcribe-panel");
const projectIdEl = document.getElementById("project-id");
const projectLabelEl = document.getElementById("project-label");
const player = document.getElementById("player");
const transcribeBtn = document.getElementById("transcribe-btn");
const transcribeStatus = document.getElementById("transcribe-status");
const separateBtn = document.getElementById("separate-btn");
const separateStatus = document.getElementById("separate-status");
const stemPlayer = document.getElementById("stem-player");
const gpuCheckbox = document.getElementById("gpu-checkbox");

const notesPanel = document.getElementById("notes-panel");
const notesTableBody = document.querySelector("#notes-table tbody");
const pianorollContainer = document.getElementById("pianoroll-container");

const playBtn = document.getElementById("play-btn");
const stopBtn = document.getElementById("stop-btn");
const testToneBtn = document.getElementById("test-tone-btn");
const octaveUpBtn = document.getElementById("octave-up-btn");
const octaveDownBtn = document.getElementById("octave-down-btn");
const deleteSelectionBtn = document.getElementById("delete-selection-btn");
const undoBtn = document.getElementById("undo-btn");
const confidenceSlider = document.getElementById("confidence-slider");
const confidenceValue = document.getElementById("confidence-value");

const arrangePanel = document.getElementById("arrange-panel");
const analyzeBtn = document.getElementById("analyze-btn");
const analyzeStatus = document.getElementById("analyze-status");
const instrumentSelect = document.getElementById("instrument-select");
const octaveShiftInput = document.getElementById("octave-shift-input");
const bpmInput = document.getElementById("bpm-input");
const gridSelect = document.getElementById("grid-select");
const swingSlider = document.getElementById("swing-slider");
const swingValue = document.getElementById("swing-value");
const computeScoreBtn = document.getElementById("compute-score-btn");
const scoreStatus = document.getElementById("score-status");
const scorePianorollContainer = document.getElementById("score-pianoroll-container");
const playScoreBtn = document.getElementById("play-score-btn");
const playConcertBtn = document.getElementById("play-concert-btn");
const stopScoreBtn = document.getElementById("stop-score-btn");

const exportPanel = document.getElementById("export-panel");
const renderStaffBtn = document.getElementById("render-staff-btn");
const exportPdfBtn = document.getElementById("export-pdf-btn");
const downloadMusicxmlLink = document.getElementById("download-musicxml");
const downloadMidiLink = document.getElementById("download-midi");
const exportStatus = document.getElementById("export-status");
const staffContainer = document.getElementById("staff-container");

let currentProjectId = null;
let pianoRoll = null;
let scorePianoRoll = null;
let lastScoreNotes = [];
let lastKeySharps = 0;
let lastScoreModel = null;
let exportedFiles = null; // { musicxml_url, midi_url } once the server export has actually run

// Mirrors core/notation.score_to_json_model, but built client-side from data
// we already have (compute-score's response) -- rendering the staff preview
// doesn't need a music21 Score or file I/O at all, only the note list. This
// is what keeps "Compute score" -> "Render staff" fast: the slow step
// (music21 building/writing MusicXML+MIDI) only runs when a download is
// actually requested, not just to preview the staff.
function buildScoreModel(notes, keySharps, bpm, timeSignature) {
  const playable = notes
    .filter((n) => !n.deleted && n.written_pitch_midi != null && n.beat != null && n.duration_beats != null)
    .sort((a, b) => a.beat - b.beat)
    .map((n) => ({
      beat: n.beat,
      duration_beats: n.duration_beats,
      written_pitch_midi: n.written_pitch_midi,
      folded: n.folded,
    }));
  return { key_sharps: keySharps, time_signature: timeSignature, bpm, notes: playable };
}

function currentScoreSettings() {
  return {
    instrument: instrumentSelect.value,
    global_octave_shift: parseInt(octaveShiftInput.value, 10) || 0,
    quantize: {
      bpm: parseFloat(bpmInput.value) || 120,
      grid: gridSelect.value,
      swing: parseFloat(swingSlider.value) || 0,
      time_signature: "4/4",
    },
  };
}

function onProjectReady(project) {
  currentProjectId = project.project_id;
  projectIdEl.textContent = project.project_id;
  projectLabelEl.textContent = project.source_label;
  player.src = api.audioUrl(project.project_id);
  transcribePanel.hidden = false;
  notesPanel.hidden = true;
  separateStatus.textContent = "";
  stemPlayer.removeAttribute("src");
  document.querySelector('input[name="stem"][value=""]').checked = true;

  gpuCheckbox.checked = false;
  gpuCheckbox.disabled = true;
  api.getSeparateCapabilities(project.project_id)
    .then((caps) => {
      gpuCheckbox.disabled = !caps.gpu_available;
      gpuCheckbox.checked = caps.gpu_available;
      gpuCheckbox.title = caps.gpu_available
        ? "CUDA GPU detected"
        : caps.demucs_available ? "No CUDA GPU detected -- separation will run on CPU" : "Demucs not installed";
    })
    .catch(() => { /* separate extra not installed; leave the checkbox disabled */ });
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  ingestStatus.textContent = `Uploading ${file.name}...`;
  try {
    const project = await api.uploadFile(file);
    ingestStatus.textContent = `Loaded: ${project.source_label}`;
    onProjectReady(project);
  } catch (e) {
    ingestStatus.textContent = `Error: ${e.message}`;
  }
});

urlSubmit.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) return;
  ingestStatus.textContent = `Downloading ${url}...`;
  urlSubmit.disabled = true;
  try {
    const project = await api.ingestUrl(url);
    ingestStatus.textContent = `Loaded: ${project.source_label}`;
    onProjectReady(project);
  } catch (e) {
    ingestStatus.textContent = `Error: ${e.message}`;
  } finally {
    urlSubmit.disabled = false;
  }
});

separateBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  const device = gpuCheckbox.checked ? "cuda" : "cpu";
  separateStatus.textContent = `Separating on ${device.toUpperCase()} (CPU can take a few minutes)...`;
  separateBtn.disabled = true;
  try {
    const result = await api.separate(currentProjectId, device);
    separateStatus.textContent = `Stems ready (${device}): ${result.stems.join(", ")}`;
  } catch (e) {
    separateStatus.textContent = `Error: ${e.message}`;
  } finally {
    separateBtn.disabled = false;
  }
});

document.querySelectorAll('input[name="stem"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    if (!currentProjectId) return;
    const stem = radio.value || null;
    stemPlayer.src = api.audioUrl(currentProjectId, stem);
  });
});

function selectedStem() {
  const checked = document.querySelector('input[name="stem"]:checked');
  return checked && checked.value ? checked.value : null;
}

transcribeBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  const stem = selectedStem();
  transcribeStatus.textContent = `Transcribing (${stem || "full mix"}, this can take a bit)...`;
  transcribeBtn.disabled = true;
  try {
    const notes = await api.transcribe(currentProjectId, { stem });
    transcribeStatus.textContent = `${notes.length} notes detected.`;
    initPianoRoll(notes);
  } catch (e) {
    transcribeStatus.textContent = `Error: ${e.message}`;
  } finally {
    transcribeBtn.disabled = false;
  }
});

function initPianoRoll(notes) {
  notesPanel.hidden = false;

  pianoRoll = new PianoRoll(pianorollContainer, {
    onEdit: async (op) => {
      const current = await api.applyEdit(currentProjectId, op);
      pianoRoll.setNotes(current);
      renderTable(current);
    },
    onSelectionChange: () => {},
  });
  pianoRoll.setNotes(notes);
  renderTable(notes);
  arrangePanel.hidden = false;
}

function renderTable(notes) {
  notesTableBody.innerHTML = "";
  let visibleCount = 0;
  notes.forEach((n, i) => {
    if (n.deleted) return;
    visibleCount++;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${i}</td><td>${n.pitch_midi}</td><td>${n.onset_s.toFixed(3)}</td><td>${n.offset_s.toFixed(3)}</td><td>${n.confidence.toFixed(2)}</td>`;
    notesTableBody.appendChild(tr);
  });
  document.getElementById("notes-count").textContent = visibleCount;
}

playBtn.addEventListener("click", async () => {
  if (!pianoRoll) return;
  playBtn.disabled = true;
  playBtn.textContent = "Loading sample...";
  try {
    const { scheduled, missing } = await saxPlayer.playNotes(pianoRoll.notes);
    transcribeStatus.textContent = missing > 0
      ? `Playing ${scheduled} notes -- ${missing} had no matching sample and were skipped silently (see console).`
      : `Playing ${scheduled} notes...`;
  } catch (e) {
    console.error("Playback failed", e);
    transcribeStatus.textContent = `Playback failed: ${e.message}`;
  } finally {
    playBtn.textContent = "▶ Play (alto sax)";
    playBtn.disabled = false;
  }
});

stopBtn.addEventListener("click", () => saxPlayer.stop());

testToneBtn.addEventListener("click", async () => {
  try {
    await saxPlayer.testTone();
    transcribeStatus.textContent = "Played a test beep -- if you didn't hear it, check system volume/output device, not this app.";
  } catch (e) {
    console.error("Test tone failed", e);
    transcribeStatus.textContent = `Test tone failed: ${e.message}`;
  }
});

octaveUpBtn.addEventListener("click", () => pianoRoll && pianoRoll.shiftSelectionOctave(1));
octaveDownBtn.addEventListener("click", () => pianoRoll && pianoRoll.shiftSelectionOctave(-1));
deleteSelectionBtn.addEventListener("click", () => pianoRoll && pianoRoll.deleteSelection());

undoBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  const current = await api.undoEdit(currentProjectId);
  pianoRoll.setNotes(current);
  renderTable(current);
});

confidenceSlider.addEventListener("input", () => {
  const v = parseFloat(confidenceSlider.value);
  confidenceValue.textContent = v.toFixed(2);
  if (pianoRoll) pianoRoll.setConfidenceThreshold(v);
});

swingSlider.addEventListener("input", () => {
  swingValue.textContent = parseFloat(swingSlider.value).toFixed(2);
});

// Any arrangement setting invalidates a previously-generated export -- the
// next download click must regenerate MusicXML/MIDI from the new settings.
[instrumentSelect, octaveShiftInput, bpmInput, gridSelect, swingSlider].forEach((el) => {
  el.addEventListener("change", () => { exportedFiles = null; });
});

analyzeBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  analyzeStatus.textContent = "Analyzing...";
  analyzeBtn.disabled = true;
  try {
    const result = await api.analyze(currentProjectId);
    analyzeStatus.textContent = `Detected: ${result.bpm} BPM, ${result.key_tonic} ${result.key_mode}`;
    bpmInput.value = Math.round(result.bpm);
  } catch (e) {
    analyzeStatus.textContent = `Error: ${e.message}`;
  } finally {
    analyzeBtn.disabled = false;
  }
});

computeScoreBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  scoreStatus.textContent = "Computing...";
  computeScoreBtn.disabled = true;
  try {
    const result = await api.computeScore(currentProjectId, currentScoreSettings());
    lastScoreNotes = result.notes;
    lastKeySharps = result.key_sharps;
    exportedFiles = null; // settings changed since the last time files were generated
    const foldedCount = result.notes.filter((n) => n.folded).length;
    scoreStatus.textContent = `${result.notes.length} notes, written key: ${result.key_sharps} sharps` +
      (foldedCount ? ` (${foldedCount} octave-folded, highlighted amber)` : "");

    if (!scorePianoRoll) {
      scorePianoRoll = new PianoRoll(scorePianorollContainer, { readOnly: true });
    }
    // Display written (transposed) pitch on the roll.
    scorePianoRoll.setNotes(result.notes.map((n) => ({ ...n, pitch_midi: n.written_pitch_midi })));
    exportPanel.hidden = false;
  } catch (e) {
    scoreStatus.textContent = `Error: ${e.message}`;
  } finally {
    computeScoreBtn.disabled = false;
  }
});

renderStaffBtn.addEventListener("click", () => {
  if (!lastScoreNotes.length) {
    exportStatus.textContent = "Compute a score first (section 4).";
    return;
  }
  // Purely client-side: no server round trip, no music21. This is what
  // makes the staff preview instant regardless of how slow MusicXML/MIDI
  // export is -- that only runs when a file is actually downloaded, below.
  const settings = currentScoreSettings();
  lastScoreModel = buildScoreModel(lastScoreNotes, lastKeySharps, settings.quantize.bpm, settings.quantize.time_signature);
  renderStaff(staffContainer, lastScoreModel);
  exportStatus.textContent = `Rendered ${lastScoreModel.notes.length} notes.`;
});

exportPdfBtn.addEventListener("click", async () => {
  try {
    await exportStaffToPdf(staffContainer, "sax2sheet-score.pdf");
  } catch (e) {
    exportStatus.textContent = `PDF export error: ${e.message}`;
  }
});

// MusicXML/MIDI actually require building a music21 Score and writing files
// server-side -- the slow step. Deferred until the user asks for one of
// these specifically, rather than running on every "Render staff" click.
async function ensureExported() {
  if (exportedFiles) return exportedFiles;
  exportStatus.textContent = "Building MusicXML/MIDI...";
  const result = await api.exportScore(currentProjectId, currentScoreSettings());
  exportedFiles = { musicxml_url: result.musicxml_url, midi_url: result.midi_url };
  return exportedFiles;
}

async function downloadExport(ev, urlKey, label) {
  ev.preventDefault();
  const link = ev.currentTarget;
  const originalText = link.textContent;
  link.textContent = `Preparing ${label}...`;
  try {
    const files = await ensureExported();
    exportStatus.textContent = `${label} ready.`;
    window.location.href = files[urlKey];
  } catch (e) {
    exportStatus.textContent = `Error: ${e.message}`;
  } finally {
    link.textContent = originalText;
  }
}

downloadMusicxmlLink.addEventListener("click", (ev) => downloadExport(ev, "musicxml_url", "MusicXML"));
downloadMidiLink.addEventListener("click", (ev) => downloadExport(ev, "midi_url", "MIDI"));

async function playScorePreview(button, pitchField) {
  if (!lastScoreNotes.length) {
    scoreStatus.textContent = "Compute a score first (no notes to play).";
    return;
  }
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Loading sample...";
  try {
    const { scheduled, missing } = await saxPlayer.playNotes(lastScoreNotes, { instrument: instrumentSelect.value, pitchField });
    scoreStatus.textContent = missing > 0
      ? `Playing ${scheduled} notes (${pitchField}) -- ${missing} had no matching sample and were skipped silently (see console).`
      : `Playing ${scheduled} notes (${pitchField})...`;
  } catch (e) {
    console.error("Playback failed", e);
    scoreStatus.textContent = `Playback failed: ${e.message}`;
  } finally {
    button.textContent = originalText;
    button.disabled = false;
  }
}

playScoreBtn.addEventListener("click", () => playScorePreview(playScoreBtn, "written"));
playConcertBtn.addEventListener("click", () => playScorePreview(playConcertBtn, "concert"));

stopScoreBtn.addEventListener("click", () => saxPlayer.stop());
