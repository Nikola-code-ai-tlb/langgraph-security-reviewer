/* ============================================================================
   SENTINEL UI controller
   Opens an SSE stream to /api/review and drives the blueprint visualization:
   nodes energize, reviewer subagents spawn in parallel, wires carry "current",
   and findings stream into the ledger.
   ========================================================================== */

const $ = (id) => document.getElementById(id);
const SEVERITIES = ["critical", "high", "medium", "low", "info"];

const els = {
  form: $("review-form"),
  target: $("target"),
  runBtn: $("run-btn"),
  modeBadge: $("mode-badge"),
  modeLabel: $("mode-label"),
  tbMode: $("tb-mode"),
  diagramSub: $("diagram-sub"),
  filesRail: $("files-rail"),
  reviewers: $("reviewers"),
  reviewersEmpty: $("reviewers-empty"),
  wires: $("wires"),
  diagram: $("diagram"),
  statusline: $("statusline"),
  statusText: $("status-text"),
  findings: $("findings"),
  findingsEmpty: $("findings-empty"),
  findingsCount: $("findings-count"),
  copyBtn: $("copy-report"),
  nodes: {
    read: $("node-read"),
    orchestrator: $("node-orchestrator"),
    reporter: $("node-reporter"),
  },
};

let source = null;          // active EventSource
let runDone = false;        // distinguishes normal stream end from error
let reviewerChips = [];     // [{el, category, state}]
let findingsCount = 0;
let latestReport = "";
const tally = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };

/* ----------------------------- bootstrap ----------------------------- */
init();
async function init() {
  bindUI();
  try {
    const res = await fetch("/api/health");
    const { mode } = await res.json();
    setMode(mode);
  } catch {
    setMode("schematic");
  }
  window.addEventListener("resize", () => requestAnimationFrame(drawWires));
}

function setMode(mode) {
  els.modeBadge.dataset.mode = mode;
  els.modeLabel.textContent = mode === "live" ? "LIVE · CLAUDE" : "SCHEMATIC";
  els.tbMode.textContent = mode === "live" ? "LIVE" : "SCHEMATIC";
}

function bindUI() {
  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = els.target.value.trim();
    if (url) startReview(url);
  });
  document.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      els.target.value = chip.dataset.url;
      startReview(chip.dataset.url);
    })
  );
  els.copyBtn.addEventListener("click", copyReport);
}

/* ----------------------------- run ----------------------------- */
function startReview(url) {
  if (source) source.close();
  resetUI();
  els.runBtn.disabled = true;
  els.target.disabled = true;
  setStatus(`Connecting to review stream...`, "working");

  runDone = false;
  source = new EventSource(`/api/review?url=${encodeURIComponent(url)}`);
  source.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
  source.onerror = () => {
    source.close();
    if (!runDone) setStatus("Stream interrupted. Check the target and try again.", "error");
    finishRun();
  };
}

function finishRun() {
  els.runBtn.disabled = false;
  els.target.disabled = false;
}

function resetUI() {
  els.filesRail.innerHTML = "";
  resetGraph();
  els.findings.querySelectorAll(".finding").forEach((n) => n.remove());
  els.findingsEmpty.style.display = "";
  findingsCount = 0;
  els.findingsCount.textContent = "0 logged";
  SEVERITIES.forEach((s) => (tally[s] = 0));
  renderTally();
  latestReport = "";
  els.copyBtn.disabled = true;
  els.diagramSub.textContent = "awaiting target";
}

function resetGraph() {
  for (const n of Object.values(els.nodes)) n.dataset.state = "idle";
  reviewerChips = [];
  els.reviewers.querySelectorAll(".reviewer-chip").forEach((c) => c.remove());
  els.reviewersEmpty.style.display = "";
  drawWires();
}

/* ----------------------------- event router ----------------------------- */
function handleEvent(evt) {
  switch (evt.type) {
    case "status":   return setStatus(evt.message, "working");
    case "target":   return onTarget(evt);
    case "files":    return onFiles(evt.files);
    case "file_start": return onFileStart(evt);
    case "node":     return onNode(evt);
    case "plan":     return onPlan(evt);
    case "reviewer": return onReviewer(evt);
    case "file_done": return onFileDone(evt);
    case "complete": return onComplete(evt);
    case "error":    return onError(evt.message);
  }
}

function onTarget(evt) {
  setMode(evt.mode);
  els.diagramSub.textContent = `${evt.kind.toUpperCase()} · ${evt.label}`;
  setStatus(`Target locked: ${evt.label}`, "working");
}

function onFiles(files) {
  els.filesRail.innerHTML = "";
  files.forEach((f) => {
    const pill = document.createElement("div");
    pill.className = "file-pill";
    pill.dataset.path = f.path;
    pill.innerHTML = `<span>${shorten(f.path)}</span><span class="ln">${f.lines} ln</span>`;
    els.filesRail.appendChild(pill);
  });
  setStatus(`${files.length} source file(s) fetched. Beginning review...`, "working");
}

function onFileStart(evt) {
  resetGraph();
  els.filesRail.querySelectorAll(".file-pill").forEach((p) => {
    if (p.dataset.path === evt.path) p.dataset.active = "true";
    else delete p.dataset.active;
  });
  els.diagramSub.textContent = `REVIEWING · ${shorten(evt.path)}`;
  setStatus(`Reading ${evt.path} (${evt.lines} lines)...`, "working");
}

function onNode(evt) {
  const node = els.nodes[evt.node];
  if (node) {
    node.dataset.state = evt.state;
    if (evt.state === "active") node.classList.add("flash");
    setTimeout(() => node && node.classList.remove("flash"), 500);
  }
  if (evt.node === "orchestrator" && evt.state === "active")
    setStatus("Orchestrator triaging risk surface...", "working");
  drawWires();
}

function onPlan(evt) {
  els.reviewersEmpty.style.display = "none";
  reviewerChips = [];
  els.reviewers.querySelectorAll(".reviewer-chip").forEach((c) => c.remove());

  evt.tasks.forEach((task, i) => {
    const chip = document.createElement("div");
    chip.className = "reviewer-chip";
    chip.dataset.state = "active"; // dispatched in parallel
    chip.style.animationDelay = `${i * 60}ms`;
    chip.innerHTML = `
      <div>
        <div class="rc-cat">${escapeHtml(task.category)}</div>
        <div class="rc-focus">${escapeHtml(task.focus || "")}</div>
      </div>
      <div class="rc-count">··</div>`;
    els.reviewers.appendChild(chip);
    reviewerChips.push({ el: chip, category: task.category, state: "active" });
  });

  setStatus(`${evt.tasks.length} reviewer subagent(s) dispatched in parallel.`, "working");
  requestAnimationFrame(drawWires);
}

function onReviewer(evt) {
  // Resolve the first still-active chip matching this category.
  const chip =
    reviewerChips.find((c) => c.category === evt.category && c.state === "active") ||
    reviewerChips.find((c) => c.state === "active");
  const n = (evt.findings || []).length;
  if (chip) {
    chip.state = n ? "flag" : "clean";
    chip.el.dataset.state = chip.state;
    chip.el.querySelector(".rc-count").textContent = n ? n : "0";
  }
  (evt.findings || []).forEach(addFinding);
  drawWires();
}

function onFileDone(evt) {
  els.nodes.reporter.dataset.state = evt.count ? "flag" : "done";
  els.filesRail.querySelectorAll(".file-pill").forEach((p) => {
    if (p.dataset.path === evt.path) {
      delete p.dataset.active;
      p.dataset.done = "true";
      if (evt.count) p.dataset.flag = "true";
    }
  });
  drawWires();
}

function onComplete(evt) {
  runDone = true;
  latestReport = evt.report || "";
  els.copyBtn.disabled = !latestReport;
  const total = evt.findings_count || 0;
  els.diagramSub.textContent = "RUN COMPLETE";
  setStatus(
    total
      ? `Review complete — ${total} finding(s) logged.`
      : "Review complete — no issues identified.",
    null
  );
  if (source) source.close();
  finishRun();
}

function onError(message) {
  runDone = true;
  setStatus(message, "error");
  if (source) source.close();
  finishRun();
}

/* ----------------------------- findings ----------------------------- */
function addFinding(f) {
  els.findingsEmpty.style.display = "none";
  findingsCount += 1;
  els.findingsCount.textContent = `${findingsCount} logged`;
  if (tally[f.severity] !== undefined) tally[f.severity] += 1;
  renderTally();

  const item = document.createElement("div");
  item.className = "finding";
  item.dataset.sev = f.severity;
  const loc = escapeHtml(`${f.file ? shorten(f.file) : ""}${f.line ? ":" + f.line : ""}`);
  item.innerHTML = `
    <div class="f-head">
      <span class="sev-tag">${escapeHtml(String(f.severity).toUpperCase())}</span>
      <span class="f-title">${escapeHtml(f.title)}</span>
      <span class="f-loc">${loc}</span>
      <span class="f-toggle">▸</span>
    </div>
    <div class="f-body"><div class="f-body-inner">
      <div class="f-meta"><span>CAT <b>${escapeHtml(f.category)}</b></span><span>CONF <b>${escapeHtml(f.confidence || "n/a")}</b></span></div>
      <div class="f-label">DIAGNOSIS</div>
      <div class="f-text">${escapeHtml(f.explanation)}</div>
      <div class="f-label">REMEDIATION</div>
      <div class="f-fix">${escapeHtml(f.suggested_fix)}</div>
    </div></div>`;
  item.querySelector(".f-head").addEventListener("click", () => item.classList.toggle("open"));
  els.findings.appendChild(item);
}

function renderTally() {
  SEVERITIES.forEach((s) => ($("t-" + s).textContent = tally[s]));
}

/* ----------------------------- wires ----------------------------- */
function drawWires() {
  const svg = els.wires;
  const base = els.diagram.getBoundingClientRect();
  svg.setAttribute("viewBox", `0 0 ${base.width} ${base.height}`);
  svg.innerHTML = "";

  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return {
      left: r.left - base.left, right: r.right - base.left,
      top: r.top - base.top, midY: r.top - base.top + r.height / 2,
    };
  };
  const path = (a, b, cls) => {
    const sx = rect(a).right, sy = rect(a).midY;
    const ex = rect(b).left, ey = rect(b).midY;
    const cx = (sx + ex) / 2;
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", `M ${sx} ${sy} C ${cx} ${sy} ${cx} ${ey} ${ex} ${ey}`);
    if (cls) p.setAttribute("class", cls);
    svg.appendChild(p);
  };

  const st = (el) => el.dataset.state;
  // read -> orchestrator
  const oState = st(els.nodes.orchestrator);
  path(els.nodes.read, els.nodes.orchestrator,
    oState === "active" ? "live" : (oState === "done" || oState === "flag") ? "done" : "");

  // orchestrator -> each reviewer chip, and chip -> reporter
  reviewerChips.forEach((c) => {
    const cls = c.state === "active" ? "live" : c.state === "flag" ? "flag" : "done";
    path(els.nodes.orchestrator, c.el, c.state === "active" ? "live" : "done");
    if (c.state !== "active") path(c.el, els.nodes.reporter, cls);
  });
}

/* ----------------------------- helpers ----------------------------- */
function setStatus(text, cls) {
  els.statusText.textContent = text;
  els.statusline.className = "statusline" + (cls ? " " + cls : "");
}
function shorten(path) {
  const parts = path.split("/");
  return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : path;
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
async function copyReport() {
  try {
    await navigator.clipboard.writeText(latestReport);
    const prev = els.copyBtn.textContent;
    els.copyBtn.textContent = "COPIED ✓";
    setTimeout(() => (els.copyBtn.textContent = prev), 1400);
  } catch {
    setStatus("Clipboard unavailable in this context.", "error");
  }
}
