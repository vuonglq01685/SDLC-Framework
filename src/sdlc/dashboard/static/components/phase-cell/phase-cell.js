/**
 * <phase-cell> custom element (Story 5.9 / UX §6.5).
 */

import { createGlyph } from "/static/components/signoff-cell/signoff-cell.js";

const CELL_STATES = ["future", "active", "complete"];

function resolveCellState(raw) {
  const key = String(raw || "future").toLowerCase();
  return CELL_STATES.includes(key) ? key : "future";
}

function parseProgress(raw) {
  const value = Number.parseInt(String(raw ?? "0"), 10);
  if (Number.isNaN(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

function renderPhaseCell(root) {
  const cellState = resolveCellState(root.getAttribute("cell-state"));
  const phaseNumber = root.getAttribute("phase-number") || "PHASE 01";
  const phaseName = root.getAttribute("phase-name") || "Phase";
  const tagLine = root.getAttribute("tag-line") || "";
  const currentItem = root.getAttribute("current-item") || "—";
  let progress = parseProgress(root.getAttribute("progress"));
  if (cellState === "complete") {
    // A complete phase reads as a full bar by definition (§6.5). JS is the
    // single source of truth for the fill width (PAT-2: the prior CSS rule
    // .phase-cell--complete .progress-fill { width: 100% } was dead — the
    // inline width below always overrode it).
    progress = 100;
  }
  const customAria = root.getAttribute("aria-label");

  root.replaceChildren();
  root.classList.remove("phase-cell", "active", "phase-cell--active", "phase-cell--complete");
  root.classList.add("phase-cell");
  if (cellState === "active") {
    root.classList.add("active", "phase-cell--active");
  } else if (cellState === "complete") {
    root.classList.add("phase-cell--complete");
  }

  root.setAttribute("role", "status");
  root.setAttribute(
    "aria-label",
    customAria || `${phaseName}, ${progress}% complete`,
  );

  const numberEl = document.createElement("div");
  numberEl.className = "phase-cell__phase-number";
  numberEl.textContent = phaseNumber;
  root.appendChild(numberEl);

  const nameEl = document.createElement("div");
  nameEl.className = "phase-cell__phase-name";
  nameEl.textContent = phaseName;
  root.appendChild(nameEl);

  const tagEl = document.createElement("div");
  tagEl.className = "phase-cell__tag-line";
  tagEl.textContent = tagLine;
  root.appendChild(tagEl);

  if (cellState === "complete") {
    root.appendChild(createGlyph("check", "phase-cell__glyph"));
  }

  const meta = document.createElement("div");
  meta.className = "phase-cell__meta";
  const itemEl = document.createElement("span");
  itemEl.textContent = currentItem;
  const pctEl = document.createElement("span");
  pctEl.textContent = `${progress}%`;
  meta.appendChild(itemEl);
  meta.appendChild(pctEl);
  root.appendChild(meta);

  const progressTrack = document.createElement("div");
  progressTrack.className = "phase-cell__progress";
  progressTrack.setAttribute("aria-hidden", "true");
  const fill = document.createElement("div");
  fill.className = "phase-cell__progress-fill";
  fill.style.width = `${progress}%`;
  progressTrack.appendChild(fill);
  root.appendChild(progressTrack);
}

class PhaseCell extends HTMLElement {
  static get observedAttributes() {
    return [
      "cell-state",
      "phase-number",
      "phase-name",
      "tag-line",
      "current-item",
      "progress",
      "aria-label",
    ];
  }

  connectedCallback() {
    this._render();
  }

  attributeChangedCallback() {
    if (this.isConnected) {
      this._render();
    }
  }

  _render() {
    renderPhaseCell(this);
  }
}

if (!customElements.get("phase-cell")) {
  customElements.define("phase-cell", PhaseCell);
}

export { CELL_STATES, parseProgress, renderPhaseCell, resolveCellState };
