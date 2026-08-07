// Thin wrapper around the backend API. No framework, no build step.
const api = {
  async uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/ingest/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async ingestUrl(url) {
    const res = await fetch("/api/ingest/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async transcribe(projectId, opts = {}) {
    const res = await fetch(`/api/projects/${projectId}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getNotes(projectId) {
    const res = await fetch(`/api/projects/${projectId}/notes`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  audioUrl(projectId, stem = null) {
    return `/api/projects/${projectId}/audio` + (stem ? `?stem=${stem}` : "");
  },

  async getCurrentNotes(projectId) {
    const res = await fetch(`/api/projects/${projectId}/notes/edits`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async applyEdit(projectId, op) {
    const res = await fetch(`/api/projects/${projectId}/notes/edits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(op),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async undoEdit(projectId) {
    const res = await fetch(`/api/projects/${projectId}/notes/edits/undo`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async clearEdits(projectId) {
    const res = await fetch(`/api/projects/${projectId}/notes/edits/clear`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async analyze(projectId) {
    const res = await fetch(`/api/projects/${projectId}/analyze`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async computeScore(projectId, settings) {
    const res = await fetch(`/api/projects/${projectId}/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async separate(projectId, device = "auto") {
    const res = await fetch(`/api/projects/${projectId}/separate?device=${device}`, { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getStems(projectId) {
    const res = await fetch(`/api/projects/${projectId}/separate`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getSeparateCapabilities(projectId) {
    const res = await fetch(`/api/projects/${projectId}/separate/capabilities`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async exportScore(projectId, settings) {
    const res = await fetch(`/api/projects/${projectId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};
