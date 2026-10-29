// Data Detective - the page logic.
// Talks to the JSON API in web_api.py. Everything from the data is put on
// the page with textContent (never innerHTML), so a CSV can't inject HTML.
"use strict";

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
const SVG_NS = "http://www.w3.org/2000/svg";
const BAND_LABELS = { good: "Good", fair: "Fair", poor: "Poor", bad: "Bad" };

const state = { caseId: null, caseName: null, view: "case", tab: "evidence" };

// ---- small helpers --------------------------------------------------------

function $(selector) {
  return document.querySelector(selector);
}

// Build an element. Children that are strings become text nodes.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Replace a node's children, skipping empty (null/false) entries, which
// replaceChildren would otherwise show as the text "null".
function fill(node, ...children) {
  node.replaceChildren(...children.flat().filter((child) => child !== null && child !== false && child !== undefined));
  return node;
}

// An icon from the sprite in index.html.
function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("en-AU");
}

// Show a number like the text report does: whole numbers without
// decimals, others to one place, tiny or huge ones in 3 significant figures.
function formatStat(value) {
  const size = Math.abs(value);
  if (size >= 1e15 || (size > 0 && size < 0.1)) return Number(value).toPrecision(3);
  if (Number.isInteger(value)) return formatNumber(value);
  return Number(value).toLocaleString("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function plural(count, word) {
  return `${formatNumber(count)} ${word}${count === 1 ? "" : "s"}`;
}

// Call the API. Returns the parsed JSON, or throws an Error whose message
// is ready to show to the user.
async function api(method, path, body, headers) {
  let reply;
  try {
    reply = await fetch(path, { method, body, headers });
  } catch (err) {
    throw new Error("Can't reach the Data Detective server. Is it still running?");
  }
  let data = {};
  try {
    data = await reply.json();
  } catch (err) {
    data = {};
  }
  if (!reply.ok) throw new Error(data.error || `The server answered ${reply.status}.`);
  return data;
}

// ---- status line, banners and busy buttons ----------------------------------

function announce(text, busy = false) {
  const status = $("#status");
  status.replaceChildren();
  if (busy) status.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  if (text) status.append(text);
}

function clearBanners() {
  $("#banners").replaceChildren();
}

function banner(kind, text) {
  const name = kind === "error" ? "bad" : kind === "success" ? "good" : "poor";
  return el("div", { class: `banner ${kind}`, role: kind === "error" ? "alert" : null },
    icon(name), el("span", {}, text));
}

function showBanner(kind, text) {
  clearBanners();
  $("#banners").append(banner(kind, text));
}

// Run an async task with a button showing a spinner and refusing clicks.
async function withBusy(button, message, task) {
  if (button) {
    if (button.getAttribute("aria-busy") === "true") return;
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    button.prepend(el("span", { class: "spinner", "aria-hidden": "true" }));
  }
  announce(message, true);
  try {
    await task();
  } catch (err) {
    showBanner("error", err.message);
    announce("");
  } finally {
    if (button) {
      button.removeAttribute("aria-busy");
      button.disabled = false;
      const spinner = button.querySelector(".spinner");
      if (spinner) spinner.remove();
    }
  }
}

// ---- theme --------------------------------------------------------------------

function currentTheme() {
  const chosen = document.documentElement.getAttribute("data-theme");
  if (chosen) return chosen;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function showThemeButton() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  const button = $("#theme-toggle");
  button.replaceChildren(icon(next === "dark" ? "moon" : "sun"),
    el("span", {}, next === "dark" ? "Dark" : "Light"));
  button.setAttribute("aria-label", `Switch to ${next} theme`);
}

function initTheme() {
  try {
    const saved = localStorage.getItem("detective-theme");
    if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
  } catch (err) { /* storage can be unavailable; the system theme is used */ }
  showThemeButton();
  $("#theme-toggle").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("detective-theme", next); } catch (err) { /* ignore */ }
    showThemeButton();
  });
}

// ---- views and tabs -----------------------------------------------------------

function setView(name) {
  state.view = name;
  for (const tab of document.querySelectorAll(".view-tab")) {
    if (tab.dataset.view === name) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  $("#case-view").hidden = name !== "case";
  $("#board-view").hidden = name !== "board";
  $("#sidebar").hidden = name !== "case";
  clearBanners();
  announce("");
  if (name === "board") renderBoardStart();
}

function setTab(name) {
  state.tab = name;
  for (const tab of document.querySelectorAll("[role=tab]")) {
    const selected = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  $("#panel-evidence").hidden = name !== "evidence";
  $("#panel-findings").hidden = name !== "findings";
}

// ---- evidence locker and uploads --------------------------------------------

async function loadLocker() {
  const list = $("#locker");
  try {
    const data = await api("GET", "/api/locker");
    list.replaceChildren();
    $("#locker-count").textContent = data.datasets.length ? String(data.datasets.length) : "";
    if (!data.datasets.length) {
      list.append(el("li", { class: "muted small" }, "No CSV files in datasets/ yet."));
    }
    for (const item of data.datasets) {
      const button = el("button", { type: "button", "data-name": item.name, title: item.name,
        onclick: () => openFromLocker(item.name, button) },
        icon("file"), el("span", { class: "name" }, item.name),
        el("span", { class: "size" }, formatBytes(item.bytes)));
      list.append(el("li", {}, button));
    }
  } catch (err) {
    list.replaceChildren(el("li", { class: "muted small" }, err.message));
  }
}

function markLocker(name) {
  for (const button of document.querySelectorAll("#locker button")) {
    if (button.dataset.name === name) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
  }
}

async function openFromLocker(name, button) {
  setView("case");
  await withBusy(button, `Opening ${name}...`, async () => {
    const data = await api("POST", "/api/cases/locker", JSON.stringify({ name }),
      { "Content-Type": "application/json" });
    markLocker(name);
    await openCase(data.case);
  }).then(() => { if (!state.caseId || state.caseName !== name) showClosedCase(); });
}

async function uploadFile(file) {
  setView("case");
  if (file.size > MAX_UPLOAD_BYTES) {
    showClosedCase();
    showBanner("error", "Files over 200 MB can't be uploaded.");
    return;
  }
  await withBusy(null, `Uploading ${file.name}...`, async () => {
    const data = await api("POST", `/api/cases/upload?name=${encodeURIComponent(file.name)}`, file);
    markLocker(null);
    await openCase(data.case);
  }).then(() => { if (!state.caseId || state.caseName !== file.name) showClosedCase(); });
}

// If opening failed, the error banner stays and the old case is closed.
function showClosedCase() {
  if (!$("#banners").childElementCount) return;
  state.caseId = null;
  state.caseName = null;
  $("#case").hidden = true;
  $("#empty-state").hidden = true;
}

function initDropzone() {
  const zone = $("#dropzone");
  const input = $("#file-input");
  input.addEventListener("change", () => {
    if (input.files.length) uploadFile(input.files[0]);
    input.value = "";
  });
  zone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  for (const name of ["dragenter", "dragover"]) {
    zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragging"); });
  }
  for (const name of ["dragleave", "drop"]) {
    zone.addEventListener(name, () => zone.classList.remove("dragging"));
  }
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) uploadFile(event.dataTransfer.files[0]);
  });
  // A file dropped anywhere else shouldn't make the browser open it.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());
}

// ---- a case: header and evidence ---------------------------------------------

async function openCase(summary) {
  state.caseId = summary.id;
  state.caseName = summary.name;
  clearBanners();
  $("#empty-state").hidden = true;
  $("#case").hidden = false;
  $("#case-name").textContent = summary.name;
  $("#case-meta").textContent = [plural(summary.rows, "row"), plural(summary.columns, "column"),
    `delimiter ${summary.delimiter}`, summary.encoding].join("  ·  ");
  const warnings = $("#case-warnings");
  warnings.replaceChildren(...summary.warnings.map(
    (text) => banner("warning", text.charAt(0).toUpperCase() + text.slice(1))));
  $("#panel-findings").replaceChildren(findingsPlaceholder());
  setTab("evidence");
  const data = await api("GET", `/api/cases/${summary.id}/evidence`);
  renderEvidence(data);
  announce(`Opened ${summary.name}.`);
}

function metric(label, value, note) {
  return el("div", { class: "metric" },
    el("div", { class: "label" }, label),
    el("div", { class: "value" }, value),
    note ? el("div", { class: "note" }, note) : null);
}

function previewTable(header, rows) {
  const head = el("tr", {}, header.map((name) => el("th", { scope: "col" }, name)));
  const body = rows.map((row) => el("tr", {}, row.map((value) => el("td", { title: value }, value))));
  return el("div", { class: "table-wrap" }, el("table", { class: "preview" },
    el("thead", {}, head), el("tbody", {}, body)));
}

function renderEvidence(data) {
  const summary = data.case;
  const panel = $("#panel-evidence");
  fill(panel,
    el("div", { class: "metrics" },
      metric("Rows", formatNumber(summary.rows)),
      metric("Columns", formatNumber(summary.columns)),
      metric("Delimiter", summary.delimiter),
      metric("Encoding", summary.encoding),
      metric("Blank lines skipped", formatNumber(data.blank_lines_skipped))),
    data.trailing_delimiters
      ? el("p", { class: "muted small section" }, "Trailing delimiters at the ends of lines were ignored.")
      : null,
    el("div", { class: "section" },
      el("div", { class: "section-title" }, el("h2", {}, "Columns"),
        el("span", { class: "muted" }, plural(data.header.length, "column"))),
      el("div", { class: "chips" }, data.header.map((name) => el("span", { class: "chip" }, name)))),
    el("div", { class: "section" },
      el("div", { class: "section-title" }, el("h2", {}, "Preview"),
        el("span", { class: "muted" }, `first ${data.preview.length} rows`)),
      previewTable(data.header, data.preview)),
    el("div", { class: "actions" },
      el("button", { type: "button", class: "button", id: "run-investigation",
        onclick: (event) => runInvestigation(event.currentTarget) },
        icon("play"), "Run investigation")));
}

// ---- findings and the case board (filled in by the next part) ---------------

function findingsPlaceholder() {
  return el("p", { class: "none-found" }, "Run the investigation to see the findings.");
}

async function runInvestigation(button) {
  showBanner("error", "Investigations aren't available yet.");
}

function renderBoardStart() {
  $("#board-view").replaceChildren(el("p", { class: "none-found" }, "The case board isn't available yet."));
}

// ---- start ------------------------------------------------------------------------

function init() {
  initTheme();
  initDropzone();
  for (const tab of document.querySelectorAll(".view-tab")) {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  }
  for (const tab of document.querySelectorAll("[role=tab]")) {
    tab.addEventListener("click", () => setTab(tab.dataset.tab));
  }
  // Arrow keys move between the Evidence and Findings tabs.
  $("[role=tablist]").addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const next = state.tab === "evidence" ? "findings" : "evidence";
    setTab(next);
    $(`#tab-${next}`).focus();
    event.preventDefault();
  });
  setTab("evidence");
  loadLocker();
}

init();
