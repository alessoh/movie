// Single-page client: upload -> start -> live progress (SSE w/ polling
// fallback) -> inline player + download. No API keys ever touch the client.
"use strict";

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const browseBtn = $("browse-btn");
const startBtn = $("start-btn");
const fileNameEl = $("file-name");
const uploadError = $("uploadError") || $("upload-error");

const uploadView = $("upload-view");
const progressView = $("progress-view");
const resultView = $("result-view");
const errorView = $("error-view");

let selectedFile = null;
let token = null;

// --- File selection -------------------------------------------------------
browseBtn.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("click", (e) => {
  if (e.target === browseBtn) return;
  fileInput.click();
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  })
);
dropzone.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});

function setFile(f) {
  selectedFile = f;
  fileNameEl.textContent = f.name;
  startBtn.disabled = false;
  uploadError.textContent = "";
}

// --- Start ----------------------------------------------------------------
startBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  startBtn.disabled = true;
  uploadError.textContent = "";

  try {
    const fd = new FormData();
    fd.append("file", selectedFile);
    const up = await fetch("/api/upload", { method: "POST", body: fd });
    if (!up.ok) throw new Error((await up.json()).detail || "Upload failed.");
    token = (await up.json()).token;

    const st = await fetch(`/api/start/${token}`, { method: "POST" });
    if (!st.ok) throw new Error((await st.json()).detail || "Could not start.");

    show(progressView);
    subscribe();
  } catch (err) {
    uploadError.textContent = err.message;
    startBtn.disabled = false;
  }
});

// --- Progress subscription (SSE with polling fallback) --------------------
function subscribe() {
  let usingPoll = false;

  try {
    const es = new EventSource(`/api/stream/${token}`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      render(data);
      if (data.ready || data.error) es.close();
    };
    es.onerror = () => {
      es.close();
      if (!usingPoll) {
        usingPoll = true;
        poll();
      }
    };
  } catch (_) {
    poll();
  }
}

async function poll() {
  try {
    const r = await fetch(`/api/status/${token}`);
    const data = await r.json();
    render(data);
    if (data.ready || data.error) return;
  } catch (_) {}
  setTimeout(poll, 1500);
}

// --- Rendering ------------------------------------------------------------
function render(data) {
  if (data.error) return showError(data.error);
  if (data.ready) return showResult();

  show(progressView);
  $("phase-label").textContent = data.phase_label || "Working…";
  $("bar-fill").style.width = (data.progress || 0) + "%";
  $("progress-pct").textContent = (data.progress || 0) + "%";

  const log = $("log");
  log.innerHTML = "";
  (data.messages || []).slice().reverse().forEach((m) => {
    const li = document.createElement("li");
    li.textContent = m;
    log.appendChild(li);
  });
}

function showResult() {
  show(resultView);
  const url = `/api/movie/${token}`;
  $("player").src = url;
  $("download-btn").href = url;
}

function showError(msg) {
  show(errorView);
  $("error-message").textContent = msg;
}

function show(view) {
  [uploadView, progressView, resultView, errorView].forEach((v) =>
    v.classList.add("hidden")
  );
  view.classList.remove("hidden");
}
