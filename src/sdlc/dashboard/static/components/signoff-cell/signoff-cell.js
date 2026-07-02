/**
 * <signoff-cell> custom element (Story 5.9 / UX §7.2).
 *
 * Data-driven four-state signoff gate cell; content-delta only (DD-06).
 */

const SIGNOFF_STATES = {
  "awaiting-signoff": {
    label: "AWAITING",
    glyph: null,
    aria: "Signoff awaiting approval",
    progress: 0,
  },
  "drafted-not-approved": {
    label: "DRAFTED",
    glyph: null,
    aria: "Signoff drafted, not approved",
    progress: 60,
  },
  approved: {
    label: "APPROVED",
    glyph: "check",
    aria: "Signoff approved, 100% complete",
    progress: 100,
  },
  "invalidated-by-replan": {
    label: "INVALIDATED",
    glyph: "slash-circle",
    aria: "Signoff invalidated by replan",
    progress: 40,
  },
};

const STATE_KEYS = Object.keys(SIGNOFF_STATES);

function resolveState(raw) {
  // Normalize case + surrounding whitespace so a valid-but-miscased state
  // (e.g. "Approved", " approved") resolves instead of silently falling back
  // to awaiting-signoff. Mirrors phase-cell.js resolveCellState (PAT-1).
  const key = String(raw || "awaiting-signoff").trim().toLowerCase();
  return STATE_KEYS.includes(key) ? key : "awaiting-signoff";
}

function setAttributeIfChanged(el, name, value) {
  // Guard against a custom-elements gotcha: setAttribute() always re-fires
  // attributeChangedCallback for an OBSERVED attribute even when the new
  // value equals the current one (the platform does not dedupe by value).
  // Calling setAttribute unconditionally from inside a render triggered by
  // that same attribute's own change is unbounded synchronous recursion.
  if (el.getAttribute(name) === value) return false;
  el.setAttribute(name, value);
  return true;
}

function createGlyph(iconId, className) {
  const wrap = document.createElement("span");
  wrap.className = className;
  wrap.setAttribute("aria-hidden", "true");

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");

  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `/static/icons/sprite.svg#${iconId}`);
  svg.appendChild(use);
  wrap.appendChild(svg);
  return wrap;
}

function renderSignoffCell(root, stateKey, config) {
  const title = root.getAttribute("title-text") || "SIGNOFF GATE";
  const item = root.getAttribute("current-item") || "—";
  const customAria = root.getAttribute("aria-label");

  root.replaceChildren();
  root.setAttribute("data-state", stateKey);
  root.setAttribute("data-signoff-state", stateKey);
  root.setAttribute("role", "status");
  setAttributeIfChanged(root, "aria-label", customAria || `${title}, ${config.aria}`);

  const header = document.createElement("div");
  header.className = "signoff-cell__header";

  const titleEl = document.createElement("span");
  titleEl.className = "signoff-cell__title";
  titleEl.textContent = title;
  header.appendChild(titleEl);

  const labelEl = document.createElement("span");
  labelEl.className = "signoff-cell__state-label";
  if (stateKey === "awaiting-signoff") {
    labelEl.classList.add("signoff-cell__state-label--mute");
  }
  labelEl.textContent = config.label;
  header.appendChild(labelEl);

  root.appendChild(header);

  if (config.glyph) {
    root.appendChild(createGlyph(config.glyph, "signoff-cell__glyph"));
  }

  const meta = document.createElement("div");
  meta.className = "signoff-cell__meta";
  const itemEl = document.createElement("span");
  itemEl.textContent = item;
  const pctEl = document.createElement("span");
  pctEl.textContent = `${config.progress}%`;
  meta.appendChild(itemEl);
  meta.appendChild(pctEl);
  root.appendChild(meta);

  const progress = document.createElement("div");
  progress.className = "signoff-cell__progress";
  progress.setAttribute("aria-hidden", "true");
  const fill = document.createElement("div");
  fill.className = "signoff-cell__progress-fill";
  progress.appendChild(fill);
  root.appendChild(progress);
}

class SignoffCell extends HTMLElement {
  static get observedAttributes() {
    return ["state", "title-text", "current-item", "aria-label"];
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
    const stateKey = resolveState(this.getAttribute("state"));
    // If normalization changes the attribute, setAttributeIfChanged's own
    // setAttribute() call re-enters attributeChangedCallback -> _render()
    // synchronously and that inner call renders with the now-normalized
    // value; returning here avoids a redundant duplicate render.
    if (setAttributeIfChanged(this, "state", stateKey)) return;
    renderSignoffCell(this, stateKey, SIGNOFF_STATES[stateKey]);
  }
}

if (!customElements.get("signoff-cell")) {
  customElements.define("signoff-cell", SignoffCell);
}

export { SIGNOFF_STATES, createGlyph, renderSignoffCell, resolveState, setAttributeIfChanged };
