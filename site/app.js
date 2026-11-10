"use strict";

const WINDSOR = [
  { id: "ambassador-bridge", name: "Ambassador Bridge" },
  { id: "windsor-and-detroit-tunnel", name: "Detroit–Windsor Tunnel" },
  { id: "gordie-howe-international-bridge", name: "Gordie Howe International Bridge" },
];
const REFRESH_MS = 60_000;
const STALE_MS = 3 * 60 * 60 * 1000;

const apiBase = (() => {
  const fromQuery = new URLSearchParams(location.search).get("api");
  const url = (fromQuery || window.BORDER_WAIT_API || "").trim();
  return url ? url.replace(/\/?$/, "/") : "";
})();
const live = Boolean(apiBase);

const $ = (id) => document.getElementById(id);
let crossings = [];

// ---------- Formatting ----------
function wait(item, prefix) {
  const status = item[`${prefix}_status`];
  const minutes = item[`${prefix}_min`];
  if (status === "reported" && minutes != null) {
    if (minutes === 0) return { text: "No delay", level: "none" };
    const level = minutes >= 45 ? "heavy" : minutes >= 20 ? "moderate" : "light";
    return { text: `${minutes} min`, level };
  }
  if (status === "closed") return { text: "Closed", level: "closed" };
  if (status === "not_applicable") return { text: "N/A", level: "na" };
  return { text: "—", level: "na", title: "Not reported" };
}

const timeFmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function updated(item) {
  const at = new Date(item.observed_at);
  const age = Date.now() - at;
  if (!live) return { text: timeFmt.format(at), stale: false };
  const stale = age > STALE_MS;
  const mins = Math.max(0, Math.round(age / 60_000));
  const text = mins < 60 ? `${mins} min ago` : mins < 24 * 60 ? `${Math.round(mins / 60)} h ago` : timeFmt.format(at);
  return { text, stale };
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null) continue;
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((c) => c != null));
  return node;
}

// ---------- Data ----------
async function getJSON(path) {
  const url = live ? new URL(path, apiBase) : "sample/crossings.json";
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

// ---------- Windsor board ----------
function sparkline(readings) {
  const points = readings
    .filter((r) => r.travellers_canada_status === "reported" && r.travellers_canada_min != null)
    .map((r) => [new Date(r.observed_at).getTime(), r.travellers_canada_min]);
  if (points.length < 2) return el("p", { class: "spark-empty" }, "Not enough readings in the last 24 hours yet.");

  const W = 240, H = 48, now = Date.now(), from = now - 24 * 3600 * 1000;
  const top = Math.max(30, ...points.map((p) => p[1]));
  const x = (t) => (((t - from) / (now - from)) * W).toFixed(1);
  const y = (m) => (H - 2 - (m / top) * (H - 4)).toFixed(1);
  const path = points.map(([t, m], i) => `${i ? "L" : "M"}${x(t)},${y(m)}`).join(" ");
  const peak = Math.max(...points.map((p) => p[1]));
  const svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" x2="${W}" y1="${H - 2}" y2="${H - 2}" class="spark-base"/>
      <path d="${path}" class="spark-line"/></svg>`;
  const figure = el("figure", { class: "spark" });
  figure.innerHTML = svg;
  figure.append(el("figcaption", {}, `Last 24 h · peak ${peak === 0 ? "no delay" : `${peak} min`}`));
  return figure;
}

function windsorCard(meta, item) {
  const card = el("article", { class: "card", "aria-labelledby": `card-${meta.id}` });
  card.append(el("h3", { id: `card-${meta.id}` }, meta.name));
  if (!item) {
    card.append(el("p", { class: "muted" }, "No reading available."));
    return card;
  }
  const travellers = wait(item, "travellers_canada");
  const commercial = wait(item, "commercial_canada");
  const when = updated(item);
  card.append(
    el("p", { class: `big level-${travellers.level}`, title: travellers.title }, travellers.text),
    el("p", { class: "card__label" }, "Travellers to Canada"),
    el(
      "dl",
      { class: "card__facts" },
      el("div", {}, el("dt", {}, "Commercial"), el("dd", { class: `level-${commercial.level}` }, commercial.text)),
      el("div", {}, el("dt", {}, "Updated"), el("dd", { class: when.stale ? "stale" : null }, when.text)),
    ),
  );
  const history = el("div", { class: "card__history", id: `history-${meta.id}` });
  history.append(
    live ? el("p", { class: "spark-empty" }, "Loading history…") : el("p", { class: "spark-empty" }, "24-hour history appears once the live API is connected."),
  );
  card.append(history);
  return card;
}

async function loadHistory(meta) {
  const target = $(`history-${meta.id}`);
  if (!target) return;
  try {
    const data = await getJSON(`crossings/${meta.id}/history`);
    target.replaceChildren(sparkline(data.readings));
  } catch {
    target.replaceChildren(el("p", { class: "spark-empty" }, "History unavailable right now."));
  }
}

function renderWindsor() {
  const byId = Object.fromEntries(crossings.map((c) => [c.crossing_id, c]));
  $("windsor").replaceChildren(...WINDSOR.map((meta) => windsorCard(meta, byId[meta.id])));
  if (live) WINDSOR.forEach(loadHistory);
}

// ---------- All crossings ----------
function renderTable() {
  const query = $("filter").value.trim().toLowerCase();
  const matches = crossings.filter((c) => `${c.office} ${c.location}`.toLowerCase().includes(query));
  $("rows").replaceChildren(
    ...matches.map((c) => {
      const travellers = wait(c, "travellers_canada");
      const commercial = wait(c, "commercial_canada");
      const when = updated(c);
      return el(
        "tr",
        {},
        el("th", { scope: "row" }, c.office, el("span", { class: "place" }, c.location)),
        el("td", { class: `num level-${travellers.level}`, title: travellers.title }, travellers.text),
        el("td", { class: `num level-${commercial.level}`, title: commercial.title }, commercial.text),
        el("td", { class: `num updated${when.stale ? " stale" : ""}` }, when.text),
      );
    }),
  );
  $("empty").hidden = matches.length > 0;
}

// ---------- Main ----------
async function refresh() {
  try {
    const data = await getJSON("crossings");
    crossings = data.crossings;
    const newest = crossings.reduce((a, c) => (c.observed_at > a ? c.observed_at : a), "");
    $("mode").className = `mode ${live ? "mode--live" : "mode--sample"}`;
    $("mode").textContent = live
      ? `Live · ${crossings.length} crossings · refreshes every minute`
      : `Sample data from ${newest ? timeFmt.format(new Date(newest)) : ""} · live API not connected`;
    $("windsor-note").textContent = "Wait to enter Canada, as estimated by CBSA.";
    renderWindsor();
    renderTable();
  } catch (error) {
    $("mode").className = "mode mode--error";
    $("mode").textContent = `Couldn't load wait times (${error.message}). Retrying…`;
  }
}

$("filter").addEventListener("input", renderTable);
refresh();
if (live) setInterval(refresh, REFRESH_MS);
