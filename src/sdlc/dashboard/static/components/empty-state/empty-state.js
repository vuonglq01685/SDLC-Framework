/**
 * Empty State (Story 5.11 / UX §6.8).
 *
 * Anti-cynicism alert-column placeholder when no STOP banners exist.
 */

import "../freshness-footer/freshness-footer.js";

/** D2: measured anti-cynicism copy — avoids banned exclamatory "All clear!" form. */
export const EMPTY_STATE_MESSAGE = "No STOPs in flight";

export function renderEmptyState(host, { message = EMPTY_STATE_MESSAGE, lastPoll, variant = "default", nowMs } = {}) {
  host.replaceChildren();
  host.classList.add("empty-state");

  const messageEl = document.createElement("p");
  messageEl.className = "empty-state__message";
  messageEl.textContent = message;

  const footer = document.createElement("freshness-footer");
  if (lastPoll != null) {
    footer.setAttribute("last-poll", String(lastPoll));
  }
  if (nowMs != null) {
    footer.setAttribute("now", String(nowMs));
  }
  footer.setAttribute("variant", variant);

  host.append(messageEl, footer);
}

class EmptyState extends HTMLElement {
  static get observedAttributes() {
    return ["message", "last-poll", "variant", "now"];
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
    const nowAttr = this.getAttribute("now");
    const nowCandidate = nowAttr != null && nowAttr !== "" ? Number(nowAttr) : Date.now();
    renderEmptyState(this, {
      message: this.getAttribute("message") || EMPTY_STATE_MESSAGE,
      lastPoll: this.getAttribute("last-poll"),
      variant: this.getAttribute("variant") || "default",
      nowMs: Number.isFinite(nowCandidate) ? nowCandidate : Date.now(),
    });
  }
}

if (!customElements.get("empty-state")) {
  customElements.define("empty-state", EmptyState);
}
