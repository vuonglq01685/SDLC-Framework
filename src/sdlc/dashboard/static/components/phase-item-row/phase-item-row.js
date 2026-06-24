/**
 * <phase-item-row> custom element (Story 5.9 AC3).
 *
 * Read-only rows; DOM order defines focus/screen-reader traversal order.
 */

import { createGlyph, resolveState } from "/static/components/signoff-cell/signoff-cell.js";

const ROW_GLYPHS = {
  "awaiting-signoff": "circle",
  "drafted-not-approved": "circle-filled",
  approved: "check",
  "invalidated-by-replan": "slash-circle",
};

function renderPhaseItemRow(root) {
  const stateKey = resolveState(root.getAttribute("state"));
  const label = root.getAttribute("label") || "Item";
  const badge = root.getAttribute("badge");

  root.replaceChildren();
  root.setAttribute("data-state", stateKey);

  const glyphId = ROW_GLYPHS[stateKey] || "circle";
  root.appendChild(createGlyph(glyphId, "phase-item-row__glyph"));

  const labelEl = document.createElement("span");
  labelEl.className = "phase-item-row__label";
  labelEl.textContent = label;
  root.appendChild(labelEl);

  if (badge) {
    const badgeEl = document.createElement("span");
    badgeEl.className = "phase-item-row__badge";
    badgeEl.textContent = badge;
    root.appendChild(badgeEl);
  }
}

class PhaseItemRow extends HTMLElement {
  static get observedAttributes() {
    return ["state", "label", "badge"];
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
    renderPhaseItemRow(this);
  }
}

if (!customElements.get("phase-item-row")) {
  customElements.define("phase-item-row", PhaseItemRow);
}

export { ROW_GLYPHS, renderPhaseItemRow };
