/**
 * <live-dot> custom element (Story 5.5 / UX §7.4).
 *
 * D2: static/components/<name>/<name>.js layout convention.
 * Renders dot + label together; variant is data-driven (DD-06 content-delta).
 */

const VARIANTS = {
  default: { label: "LIVE", pulse: "live-dot-pulse" },
  warn: { label: "WARN", pulse: "live-dot-pulse--stop" },
  disconnected: { label: "DISCONNECTED", pulse: "live-dot-pulse--stop" },
};

function resolveVariant(raw) {
  const key = String(raw || "default").toLowerCase();
  return VARIANTS[key] ? key : "default";
}

function renderLiveDot(root, variantKey) {
  const config = VARIANTS[variantKey];
  root.replaceChildren();

  const dot = document.createElement("span");
  dot.className = `live-dot__dot ${config.pulse}`;
  dot.setAttribute("aria-hidden", "true");

  const label = document.createElement("span");
  label.className = "live-dot__label";
  label.textContent = config.label;

  root.appendChild(dot);
  root.appendChild(label);
}

class LiveDot extends HTMLElement {
  static get observedAttributes() {
    return ["variant"];
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
    const variantKey = resolveVariant(this.getAttribute("variant"));
    this.setAttribute("variant", variantKey);
    renderLiveDot(this, variantKey);
  }
}

if (!customElements.get("live-dot")) {
  customElements.define("live-dot", LiveDot);
}

export { VARIANTS, renderLiveDot, resolveVariant };
