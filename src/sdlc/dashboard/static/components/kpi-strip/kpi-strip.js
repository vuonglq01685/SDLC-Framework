/**
 * <kpi-strip> custom element (Story 5.7 / UX §6.3).
 *
 * Five even KPI cells: default / no-data (n/a) / stale (as of HH:MM:SS).
 * Synthetic fixtures only — real DORA wiring is Story 5.17.
 */

import { formatLocalTime } from "../freshness-footer/freshness-footer.js";

const KPI_STATES = ["default", "no-data", "stale"];

function resolveState(raw) {
  const key = String(raw || "default").trim().toLowerCase();
  return KPI_STATES.includes(key) ? key : "default";
}

function formatDeltaLine(direction, text) {
  const arrowByDirection = { up: "\u2191", down: "\u2193", neutral: "\u2014" };
  const arrow = arrowByDirection[direction] || arrowByDirection.neutral;
  const prefix = direction === "up" && !String(text).trim().startsWith("+") ? `+${text}` : text;
  return `${arrow} ${prefix}`.trim();
}

function renderNoDataValue(dl, { label, reason, reasonId }) {
  const dt = document.createElement("dt");
  dt.className = "kpi-strip__label";
  dt.textContent = label;

  const dd = document.createElement("dd");
  dd.className = "kpi-strip__value kpi-strip__value--no-data";
  dd.textContent = "n/a";
  dd.setAttribute("aria-describedby", reasonId);

  // `<dd>` (not a bare `<span>`) keeps the `<dl>` content model valid; it is
  // sr-only and referenced by the value cell's aria-describedby.
  const reasonEl = document.createElement("dd");
  reasonEl.id = reasonId;
  reasonEl.className = "kpi-strip__sr-only";
  reasonEl.textContent = reason || "No data available";

  dl.append(dt, dd, reasonEl);
}

function renderStaleDelta(staleAt) {
  const dd = document.createElement("dd");
  dd.className = "kpi-strip__delta kpi-strip__delta--stale";
  const when = staleAt instanceof Date && !Number.isNaN(staleAt.getTime())
    ? staleAt
    : new Date();
  dd.textContent = `as of ${formatLocalTime(when)}`;
  return dd;
}

function appendValueWithUnit(parent, { value, unit, stale }) {
  const hero = document.createElement("span");
  hero.className = "kpi-strip__hero";
  if (stale) {
    hero.classList.add("kpi-strip__hero--stale");
  }
  hero.textContent = value;

  parent.appendChild(hero);

  if (unit) {
    const unitEl = document.createElement("span");
    unitEl.className = "kpi-strip__unit";
    unitEl.textContent = unit;
    parent.appendChild(unitEl);
  }
}

function renderKpiCell(cell, index) {
  // Guard non-object entries (e.g. a malformed `fixture="[null]"`) so one bad cell
  // renders a placeholder instead of throwing and aborting the whole strip.
  const safeCell = cell && typeof cell === "object" ? cell : {};
  const state = resolveState(safeCell.state);
  const wrap = document.createElement("div");
  wrap.className = "kpi-strip__cell";
  wrap.setAttribute("data-state", state);

  const dl = document.createElement("dl");
  dl.className = "kpi-strip__cell-dl";

  if (state === "no-data") {
    renderNoDataValue(dl, {
      label: safeCell.label ?? "—",
      reason: safeCell.noDataReason,
      reasonId: `kpi-no-data-reason-${index}`,
    });
    wrap.appendChild(dl);
    return wrap;
  }

  const dt = document.createElement("dt");
  dt.className = "kpi-strip__label";
  dt.textContent = safeCell.label ?? "—";

  const valueDd = document.createElement("dd");
  valueDd.className = "kpi-strip__value";
  if (state === "stale") {
    valueDd.classList.add("kpi-strip__value--stale");
  }
  appendValueWithUnit(valueDd, {
    value: safeCell.value ?? "—",
    unit: safeCell.unit,
    stale: state === "stale",
  });

  dl.append(dt, valueDd);

  if (state === "stale") {
    const staleAt = safeCell.staleAt ? new Date(safeCell.staleAt) : new Date();
    dl.appendChild(renderStaleDelta(staleAt));
  } else if (safeCell.delta) {
    const deltaDd = document.createElement("dd");
    const direction = safeCell.delta.direction || "neutral";
    deltaDd.className = `kpi-strip__delta kpi-strip__delta--${direction}`;
    deltaDd.textContent = formatDeltaLine(direction, safeCell.delta.text || "");
    dl.appendChild(deltaDd);
  }

  wrap.appendChild(dl);
  return wrap;
}

function renderKpiStrip(root, cells) {
  root.replaceChildren();

  const section = document.createElement("section");
  section.className = "kpi-strip";
  section.setAttribute("role", "region");
  section.setAttribute("aria-label", "Project KPIs");

  const list = Array.isArray(cells) ? cells.slice(0, 5) : [];
  while (list.length < 5) {
    list.push({ label: "—", state: "no-data", noDataReason: "Placeholder cell" });
  }

  list.forEach((cell, index) => {
    section.appendChild(renderKpiCell(cell, index));
  });

  root.appendChild(section);
}

/** Synthetic fixture exercising default / no-data / stale (Story 5.7). */
export const SYNTHETIC_KPI_FIXTURE = [
  {
    label: "DEPLOY FREQUENCY",
    state: "default",
    value: "2.4",
    unit: "/day",
    delta: { direction: "up", text: "0.8 vs last 7d" },
  },
  {
    label: "LEAD TIME FOR CHANGES",
    state: "default",
    value: "18",
    unit: "hrs",
    delta: { direction: "down", text: "3 vs last 7d" },
  },
  {
    label: "MTTR",
    state: "default",
    value: "42",
    unit: "min",
    delta: { direction: "neutral", text: "0 vs last 7d" },
  },
  {
    label: "CHANGE FAIL RATE",
    state: "no-data",
    noDataReason: "No deployments recorded in the last 7 days",
  },
  {
    label: "RECOVERY TIME",
    state: "stale",
    value: "1.2",
    unit: "hrs",
    staleAt: "2026-06-25T14:32:05",
  },
];

class KpiStrip extends HTMLElement {
  connectedCallback() {
    const raw = this.getAttribute("fixture");
    let cells = SYNTHETIC_KPI_FIXTURE;
    if (raw) {
      try {
        cells = JSON.parse(raw);
      } catch {
        cells = SYNTHETIC_KPI_FIXTURE;
      }
    }
    renderKpiStrip(this, cells);
  }
}

if (!customElements.get("kpi-strip")) {
  customElements.define("kpi-strip", KpiStrip);
}

export {
  KPI_STATES,
  formatDeltaLine,
  renderKpiCell,
  renderKpiStrip,
  renderNoDataValue,
  renderStaleDelta,
  resolveState,
};
