/**
 * <freshness-footer> custom element (Story 5.5 / UX §7.5).
 *
 * Left: "as of HH:MM:SS" (local). Right: <live-dot> + label.
 * Stale when last poll is older than 30s -> timestamp uses --ink-mute.
 */

import "../live-dot/live-dot.js";

const STALE_MS = 30_000;

function formatLocalTime(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function parseLastPoll(raw) {
  if (raw == null || raw === "") {
    return null;
  }
  const numeric = Number(raw);
  if (!Number.isNaN(numeric) && Number.isFinite(numeric)) {
    const fromNumeric = new Date(numeric);
    return Number.isNaN(fromNumeric.getTime()) ? null : fromNumeric;
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function isStale(lastPoll, nowMs) {
  if (!lastPoll) {
    return true;
  }
  return nowMs - lastPoll.getTime() > STALE_MS;
}

function renderFreshnessFooter(root, { lastPoll, variant, nowMs }) {
  root.replaceChildren();

  const timestamp = document.createElement("span");
  timestamp.className = "freshness-footer__timestamp";
  if (lastPoll) {
    timestamp.textContent = `as of ${formatLocalTime(lastPoll)}`;
    if (!isStale(lastPoll, nowMs)) {
      timestamp.classList.add("freshness-footer__timestamp--fresh");
    }
  } else {
    timestamp.textContent = "as of --:--:--";
  }

  const status = document.createElement("span");
  status.className = "freshness-footer__status";

  const dot = document.createElement("live-dot");
  dot.setAttribute("variant", variant || "default");
  status.appendChild(dot);

  root.appendChild(timestamp);
  root.appendChild(status);
}

class FreshnessFooter extends HTMLElement {
  static get observedAttributes() {
    return ["last-poll", "variant", "now"];
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
    const lastPoll = parseLastPoll(this.getAttribute("last-poll"));
    const nowAttr = this.getAttribute("now");
    const nowCandidate =
      nowAttr != null && nowAttr !== "" ? Number(nowAttr) : Date.now();
    const nowMs = Number.isFinite(nowCandidate) ? nowCandidate : Date.now();
    const variant = this.getAttribute("variant") || "default";
    renderFreshnessFooter(this, { lastPoll, variant, nowMs });
  }
}

if (!customElements.get("freshness-footer")) {
  customElements.define("freshness-footer", FreshnessFooter);
}

export {
  STALE_MS,
  formatLocalTime,
  isStale,
  parseLastPoll,
  renderFreshnessFooter,
};
