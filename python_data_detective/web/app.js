// Data Detective - the page logic.
// Talks to the JSON API in web_api.py. Everything from the data is put on
// the page with textContent (never innerHTML), so a CSV can't inject HTML.
"use strict";

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
const SVG_NS = "http://www.w3.org/2000/svg";
const BAND_LABELS = { good: "Good", fair: "Fair", poor: "Poor", bad: "Bad" };
const CHIP_LIMIT = 60;

const state = { caseId: null, caseName: null, view: "case", tab: "evidence", board: null };

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

// Send a request. Returns the reply, or throws an Error whose message is
// ready to show to the user.
async function send(method, path, body, headers) {
  let reply;
  try {
    reply = await fetch(path, { method, body, headers });
  } catch (err) {
    throw new Error("Can't reach the Data Detective server. Is it still running?");
  }
  if (!reply.ok) {
    let data = {};
    try {
      data = await reply.json();
    } catch (err) {
      data = {};
    }
    throw new Error(data.error || `The server answered ${reply.status}.`);
  }
  return reply;
}

// Call the JSON API and return the parsed answer.
async function api(method, path, body, headers) {
  const reply = await send(method, path, body, headers);
  try {
    return await reply.json();
  } catch (err) {
    throw new Error("The server's answer couldn't be read.");
  }
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
// Disabling a button takes the keyboard focus away, so it is given back.
async function withBusy(button, message, task) {
  const hadFocus = Boolean(button) && document.activeElement === button;
  if (button) {
    if (button.getAttribute("aria-busy") === "true") return;
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    button.prepend(el("span", { class: "spinner", "aria-hidden": "true" }));
  }
  clearBanners();
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
      const focusLost = !document.activeElement || document.activeElement === document.body;
      if (hadFocus && focusLost && button.isConnected && !button.closest("[hidden]")) button.focus();
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
  $(".layout").classList.toggle("no-sidebar", name !== "case");
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
  await withBusy(button, `Opening ${name}…`, async () => {
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
  await withBusy(null, `Uploading ${file.name}…`, async () => {
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
      columnChips(data.header)),
    el("div", { class: "section" },
      el("div", { class: "section-title" }, el("h2", {}, "Preview"),
        el("span", { class: "muted" }, `first ${data.preview.length} rows`)),
      previewTable(data.header, data.preview)),
    el("div", { class: "actions" },
      el("button", { type: "button", class: "button", id: "run-investigation",
        onclick: (event) => runInvestigation(event.currentTarget) },
        icon("play"), "Run investigation")));
}

// A very wide file would bury the page in chips, so long lists start short.
function columnChips(header) {
  const chips = el("div", { class: "chips" });
  const chip = (name) => el("span", { class: "chip" }, name);
  const showAll = () => fill(chips, header.map(chip));
  if (header.length <= CHIP_LIMIT) return showAll();
  return fill(chips, header.slice(0, CHIP_LIMIT).map(chip),
    el("button", { type: "button", class: "chip more-chip", onclick: showAll },
      `Show all ${formatNumber(header.length)} columns`));
}

// ---- tables and badges --------------------------------------------------------

// The band for a score: the same thresholds as the verdicts.
function scoreBand(score) {
  if (score >= 95) return "good";
  if (score >= 85) return "fair";
  if (score >= 70) return "poor";
  return "bad";
}

// A badge always pairs the band's colour with an icon and words.
function badge(band, text, title) {
  return el("span", { class: `verdict band-${band}`, title: title || null }, icon(band), text);
}

function bar(score, band) {
  const width = Math.max(0, Math.min(100, score));
  return el("div", { class: "bar", "aria-hidden": "true" },
    el("div", { class: `bar-fill band-${band}`, style: `width: ${width}%` }));
}

function cell(content, options = {}) {
  const classes = [options.num ? "num" : "", options.mono ? "mono" : "", options.class || ""];
  return el("td", { class: classes.filter(Boolean).join(" ") || null, "data-sort": options.sort ?? null }, content);
}

// A table of rows (arrays of cells, or ready-made <tr>s), or "None found".
// Columns are labels, or {label, num} for right-aligned number columns.
function dataTable(columns, rows, options = {}) {
  if (!rows.length) return el("p", { class: "none-found" }, "None found");
  const head = el("tr", {}, columns.map((column, index) => {
    const label = column.label ?? column;
    return el("th", { scope: "col", class: column.num ? "num" : null },
      options.sortable
        ? el("button", { type: "button", class: "sort",
          onclick: (event) => sortTable(event.currentTarget.closest("table"), index) }, label)
        : label);
  }));
  const body = rows.map((row) => (row instanceof Node ? row : el("tr", {}, row)));
  return el("div", { class: `table-wrap scroll${options.compact ? " compact" : ""}` },
    el("table", { class: options.class || null }, el("thead", {}, head), el("tbody", {}, body)));
}

// Sort a table's rows by one column; clicking the same header again
// reverses the order. Numbers sort as numbers (a cell's data-sort value
// is used when it has one).
function sortTable(table, columnIndex) {
  const headers = [...table.tHead.rows[0].cells];
  const ascending = headers[columnIndex].getAttribute("aria-sort") !== "ascending";
  const body = table.tBodies[0];
  const rows = [...body.rows];
  const keyOf = (row) => row.cells[columnIndex].dataset.sort ?? row.cells[columnIndex].textContent;
  const numeric = rows.every((row) => keyOf(row).trim() !== "" && Number.isFinite(Number(keyOf(row))));
  rows.sort((a, b) => {
    const order = numeric
      ? Number(keyOf(a)) - Number(keyOf(b))
      : keyOf(a).localeCompare(keyOf(b), "en", { numeric: true, sensitivity: "base" });
    return ascending ? order : -order;
  });
  body.append(...rows);
  headers.forEach((header, index) => {
    if (index === columnIndex) header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
    else header.removeAttribute("aria-sort");
  });
}

function section(title, count, ...content) {
  return el("div", { class: "section" },
    el("div", { class: "section-title" }, el("h2", {}, title),
      count ? el("span", { class: "muted" }, count) : null),
    ...content);
}

function moreNote(shown, total) {
  if (total <= shown) return null;
  return el("p", { class: "muted small more" }, `…and ${formatNumber(total - shown)} more`);
}

// ---- findings -----------------------------------------------------------------

function findingsPlaceholder() {
  return el("div", { class: "placeholder" },
    el("p", { class: "none-found" }, "Run the investigation to see the findings."),
    el("button", { type: "button", class: "button", onclick: (event) => runInvestigation(event.currentTarget) },
      icon("play"), "Run investigation"));
}

async function runInvestigation(button) {
  const id = state.caseId;
  const name = state.caseName;
  if (!id) return;
  const hadFocus = Boolean(button) && document.activeElement === button;
  await withBusy(button, `Investigating ${name}…`, async () => {
    const data = await api("POST", `/api/cases/${id}/investigate`);
    if (state.caseId !== id) return;   // another case was opened meanwhile
    renderFindings(data);
    setTab("findings");
    if (hadFocus) $("#tab-findings").focus();
    announce(`Investigation complete: ${name} scored ${data.score}/100.`);
  });
}

function problemCount(suspect) {
  const parts = [];
  if (suspect.invalid) parts.push(`${formatNumber(suspect.invalid)} invalid`);
  if (suspect.not_numbers) parts.push(`${formatNumber(suspect.not_numbers)} not numbers`);
  return parts.length ? parts.join(", ") : "0";
}

function examples(list) {
  if (!list.length) return el("span", { class: "muted" }, "—");
  return list.flatMap((example, index) => [index ? ", " : null,
    el("span", { class: "mono" }, example.value), ` (line ${example.line})`]);
}

function profileSummary(profile) {
  if (profile.stats) {
    const s = profile.stats;
    return `min ${formatStat(s.min)} · max ${formatStat(s.max)} · mean ${formatStat(s.mean)} · median ${formatStat(s.median)}`;
  }
  if (profile.most_common) {
    return [`${formatNumber(profile.unique)} unique · most common `,
      el("span", { class: "mono" }, profile.most_common.value), ` (${formatNumber(profile.most_common.count)})`];
  }
  return "all values missing";
}

function renderFindings(data) {
  const time = new Date(data.investigated_at);
  const when = Number.isNaN(time.getTime()) ? data.investigated_at
    : time.toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" });
  const scoreCard = el("div", { class: "metric score-card" },
    el("div", { class: "label" }, "Quality score"),
    el("div", { class: "score" }, String(data.score), el("span", {}, " /100")),
    badge(data.band, data.verdict),
    el("div", { class: "note" }, `Case file #${data.case_number} · ${when}`));
  const subScores = data.sub_scores.map((sub) => {
    const band = scoreBand(sub.score);
    return el("div", { class: "metric sub-score" },
      el("div", { class: "label" }, sub.name),
      el("div", { class: "sub-score-line" },
        el("span", { class: "value" }, sub.score.toFixed(1)), badge(band, BAND_LABELS[band])),
      bar(sub.score, band),
      el("div", { class: "note" }, sub.note));
  });
  const reportPath = `/api/cases/${data.case.id}/report.txt`;
  const duplicates = data.duplicates;
  const malformed = data.malformed;
  fill($("#panel-findings"),
    el("div", { class: "score-row" }, scoreCard, subScores),
    el("div", { class: "actions section" },
      el("button", { type: "button", class: "button", onclick: (event) => saveReport(event.currentTarget) },
        icon("save"), "Save to reports/"),
      el("a", { class: "button secondary", href: reportPath, download: true,
        onclick: (event) => { event.preventDefault(); downloadReport(event.currentTarget); } },
        icon("download"), "Download .txt")),
    section("Suspects", data.suspects.length ? plural(data.suspects.length, "column") : null,
      dataTable(["Column", "Type", { label: "Missing", num: true }, { label: "Invalid / not numbers", num: true }, "Examples"],
        data.suspects.map((suspect) => [cell(suspect.column, { mono: true }), cell(suspect.kind),
          cell(formatNumber(suspect.missing), { num: true }), cell(problemCount(suspect), { num: true }),
          cell(examples(suspect.examples), { class: "examples" })]))),
    section("Duplicates", duplicates.total ? plural(duplicates.total, "duplicate row") : null,
      dataTable([{ label: "Line", num: true }, { label: "Duplicates line", num: true }],
        duplicates.items.map((item) => [cell(formatNumber(item.line), { num: true }),
          cell(formatNumber(item.original), { num: true })]),
        { compact: true }),
      moreNote(duplicates.items.length, duplicates.total)),
    section("Malformed rows", malformed.total ? plural(malformed.total, "malformed row") : null,
      dataTable([{ label: "Line", num: true }, { label: "Fields", num: true }, { label: "Expected", num: true }],
        malformed.items.map((item) => [cell(formatNumber(item.line), { num: true }),
          cell(formatNumber(item.fields), { num: true }), cell(formatNumber(malformed.expected_fields), { num: true })]),
        { compact: true }),
      moreNote(malformed.items.length, malformed.total)),
    section("Column profiles", plural(data.profiles.length, "column"),
      dataTable(["Column", "Type", { label: "Missing", num: true }, "Summary"],
        data.profiles.map((profile) => [cell(profile.column, { mono: true }), cell(profile.kind),
          cell(`${profile.missing_percent.toFixed(1)}%`, { num: true, sort: profile.missing_percent }),
          cell(profileSummary(profile))]),
        { sortable: true })));
}

async function saveReport(button) {
  const id = state.caseId;
  await withBusy(button, `Saving the report for ${state.caseName}…`, async () => {
    const data = await api("POST", `/api/cases/${id}/save`);
    const text = `Saved to ${data.path}${data.replaced ? " (replaced the previous report)" : ""}`;
    showBanner("success", text);
    announce(text);
  });
}

// The file name the server gave the report, from Content-Disposition.
function reportFileName(header) {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header || "");
  if (encoded) {
    try { return decodeURIComponent(encoded[1]); } catch (err) { /* use the plain name */ }
  }
  const plain = /filename="([^"]+)"/i.exec(header || "");
  return plain ? plain[1] : "report.txt";
}

// The download is fetched first, so a closed case or a stopped server
// shows a banner instead of saving an error page as the report.
async function downloadReport(link) {
  await withBusy(link, "Preparing the report…", async () => {
    const reply = await send("GET", link.getAttribute("href"));
    const url = URL.createObjectURL(await reply.blob());
    const save = el("a", { href: url, download: reportFileName(reply.headers.get("Content-Disposition")) });
    document.body.append(save);
    save.click();
    save.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    announce("Report downloaded.");
  });
}

// ---- case board -----------------------------------------------------------------

function renderBoardStart() {
  fill($("#board-view"),
    el("div", { class: "board-head" },
      el("div", {}, el("h1", {}, "Case board"),
        el("p", { class: "muted" }, "Investigate every dataset in the evidence locker and rank them by quality score.")),
      el("button", { type: "button", class: "button", onclick: (event) => investigateAll(event.currentTarget) },
        icon("play"), "Investigate all datasets")),
    el("div", { id: "board-results" }));
  if (state.board) renderBoard(state.board);
  else fill($("#board-results"), el("p", { class: "none-found" }, "No datasets ranked yet."));
}

async function investigateAll(button) {
  await withBusy(button, "Investigating every dataset in the locker…", async () => {
    const data = await api("POST", "/api/investigate-all");
    state.board = data;
    renderBoard(data);
    const failed = data.failures.length ? ` ${formatNumber(data.failures.length)} couldn't be opened.` : "";
    announce(`Ranked ${plural(data.ranked.length, "dataset")}.${failed}`);
  });
}

function renderBoard(data) {
  const rows = data.ranked.map((item) => {
    const open = () => openFromBoard(item.name);
    return el("tr", { class: "clickable", onclick: open },
      cell(String(item.rank), { num: true }),
      el("td", {}, el("button", { type: "button", class: "link-button",
        onclick: (event) => { event.stopPropagation(); open(); } }, item.name)),
      cell(formatNumber(item.rows), { num: true }),
      el("td", {}, el("div", { class: "board-bar" }, bar(item.score, item.band),
        el("span", { class: "score-number" }, String(item.score)))),
      el("td", {}, badge(item.band, item.short_verdict, item.verdict)));
  });
  fill($("#board-results"),
    section("Ranking", plural(data.ranked.length, "dataset"),
      dataTable([{ label: "Rank", num: true }, "Dataset", { label: "Rows", num: true }, "Score", "Verdict"],
        rows, { class: "board" })),
    data.failures.length
      ? section("Couldn't open", plural(data.failures.length, "file"),
        el("ul", { class: "failures" }, data.failures.map((failure) =>
          el("li", {}, el("span", { class: "mono" }, failure.name), ` — ${failure.reason}`))))
      : null,
    el("div", { class: "actions" },
      el("button", { type: "button", class: "button secondary", onclick: (event) => saveAll(event.currentTarget) },
        icon("save"), "Save all reports")));
}

// Open a ranked dataset as a case and show its findings.
async function openFromBoard(name) {
  const button = [...document.querySelectorAll("#locker button")].find((item) => item.dataset.name === name);
  await openFromLocker(name, button || null);
  if (state.caseId && state.caseName === name) await runInvestigation($("#run-investigation"));
}

async function saveAll(button) {
  await withBusy(button, "Saving every report…", async () => {
    const data = await api("POST", "/api/save-all");
    const text = `Saved ${plural(data.saved, "case report")} and leaderboard.txt to ${data.folder}/`;
    showBanner("success", text);
    announce(text);
  });
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
