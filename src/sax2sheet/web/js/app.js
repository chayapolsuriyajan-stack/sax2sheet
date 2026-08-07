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

const notesPanel = document.getElementById("notes-panel");
const notesTableBody = document.querySelector("#notes-table tbody");
const pianorollContainer = document.getElementById("pianoroll-container");

const playBtn = document.getElementById("play-btn");
const stopBtn = document.getElementById("stop-btn");
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
let lastScoreModel = null;

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
  separateStatus.textContent = "Separating (can take a few minutes on CPU)...";
  separateBtn.disabled = true;
  try {
    const result = await api.separate(currentProjectId);
    separateStatus.textContent = `Stems ready: ${result.stems.join(", ")}`;
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
  notes.forEach((n, i) => {
    if (n.deleted) return;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${i}</td><td>${n.pitch_midi}</td><td>${n.onset_s.toFixed(3)}</td><td>${n.offset_s.toFixed(3)}</td><td>${n.confidence.toFixed(2)}</td>`;
    notesTableBody.appendChild(tr);
  });
}

playBtn.addEventListener("click", async () => {
  if (!pianoRoll) return;
  playBtn.disabled = true;
  playBtn.textContent = "Loading sample...";
  try {
    await saxPlayer.playNotes(pianoRoll.notes);
    playBtn.textContent = "▶ Play (alto sax)";
  } catch (e) {
    playBtn.textContent = "▶ Play (alto sax)";
    alert(`Playback failed: ${e.message}`);
  } finally {
    playBtn.disabled = false;
  }
});

stopBtn.addEventListener("click", () => saxPlayer.stop());

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

renderStaffBtn.addEventListener("click", async () => {
  if (!currentProjectId) return;
  exportStatus.textContent = "Exporting...";
  renderStaffBtn.disabled = true;
  try {
    const result = await api.exportScore(currentProjectId, currentScoreSettings());
    lastScoreModel = result.score_model;
    renderStaff(staffContainer, lastScoreModel);
    downloadMusicxmlLink.href = result.musicxml_url;
    downloadMidiLink.href = result.midi_url;
    exportStatus.textContent = `Rendered ${lastScoreModel.notes.length} notes.`;
  } catch (e) {
    exportStatus.textContent = `Error: ${e.message}`;
  } finally {
    renderStaffBtn.disabled = false;
  }
});

exportPdfBtn.addEventListener("click", async () => {
  try {
    await exportStaffToPdf(staffContainer, "sax2sheet-score.pdf");
  } catch (e) {
    exportStatus.textContent = `PDF export error: ${e.message}`;
  }
});

playScoreBtn.addEventListener("click", async () => {
  if (!lastScoreNotes.length) return;
  await saxPlayer.playNotes(lastScoreNotes, { instrument: instrumentSelect.value, pitchField: "written" });
});

playConcertBtn.addEventListener("click", async () => {
  if (!lastScoreNotes.length) return;
  await saxPlayer.playNotes(lastScoreNotes, { instrument: instrumentSelect.value, pitchField: "concert" });
});

stopScoreBtn.addEventListener("click", () => saxPlayer.stop());
