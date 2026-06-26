/**
 * <resume-card> custom element (Story 5.8 / UX §6.4).
 */

import "../freshness-footer/freshness-footer.js";
import { createGlyph } from "../signoff-cell/signoff-cell.js";

const GREETING_STORAGE_KEY = "sdlc.resume-card.greetingShown";
const COPY_FEEDBACK_MS = 1_000;
const COPY_ARIA_LABEL = "Copy suggested command";
const COPY_LIVE_MESSAGE = "copied to clipboard";
const SHELL_PREFIX_RE = /^[$>❯]\s*/u;

function normalizeCommand(raw) {
  if (raw == null) {
    return "";
  }
  let text = String(raw).trim();
  text = text.replace(SHELL_PREFIX_RE, "");
  return text.trim();
}

function readGreetingFlag(storage) {
  try {
    return storage.getItem(GREETING_STORAGE_KEY) === "1";
  } catch {
    return true;
  }
}

function shouldShowGreeting(storage) {
  return !readGreetingFlag(storage);
}

function markGreetingShown(storage) {
  try {
    storage.setItem(GREETING_STORAGE_KEY, "1");
  } catch {
    // sessionStorage may be unavailable in restricted contexts
  }
}

function parseBreadcrumb(raw) {
  if (Array.isArray(raw)) {
    return raw.map((part) => String(part).trim()).filter(Boolean);
  }
  if (raw == null || raw === "") {
    return [];
  }
  const text = String(raw).trim();
  if (text.startsWith("[")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map((part) => String(part).trim()).filter(Boolean);
      }
    } catch {
      return text.split("/").map((part) => part.trim()).filter(Boolean);
    }
  }
  return text.split("/").map((part) => part.trim()).filter(Boolean);
}

function formatBreadcrumb(parts) {
  return parts.join(" / ");
}

function ensureLiveRegion(root) {
  let region = root.querySelector(":scope > .resume-card__live-region");
  if (!region) {
    region = document.createElement("div");
    region.className = "resume-card__live-region resume-card__sr-only";
    region.setAttribute("aria-live", "polite");
    region.setAttribute("aria-atomic", "true");
    root.appendChild(region);
  }
  return region;
}

function swapCopyGlyph(button, iconId) {
  const use = button.querySelector("use");
  if (use) {
    use.setAttribute("href", `/static/icons/sprite.svg#${iconId}`);
  }
}

function bindCopyButton(button, command, liveRegion, { clipboard = navigator.clipboard, feedbackMs = COPY_FEEDBACK_MS } = {}) {
  let resetHandle = null;
  button.addEventListener("click", async () => {
    const normalized = normalizeCommand(command);
    try {
      await clipboard.writeText(normalized);
    } catch {
      // Deliberate no-op: a copy failure (clipboard unavailable in an insecure
      // context, or writeText rejected) leaves the button idle — no icon swap,
      // no announcement. The disabled / disconnected-copy state is Story 5.20;
      // until then no failure UI is surfaced here.
      return;
    }
    swapCopyGlyph(button, "check");
    liveRegion.textContent = COPY_LIVE_MESSAGE;
    if (resetHandle != null) {
      window.clearTimeout(resetHandle);
    }
    resetHandle = window.setTimeout(() => {
      swapCopyGlyph(button, "copy");
      resetHandle = null;
    }, feedbackMs);
  });
}

function renderResumeCard(root, data, { storage = sessionStorage, forceGreeting } = {}) {
  const liveRegion = ensureLiveRegion(root);
  root.querySelectorAll(":scope > .resume-card").forEach((node) => node.remove());

  const card = document.createElement("section");
  card.className = "resume-card";
  card.setAttribute("role", "region");
  card.setAttribute("aria-label", "Resume position and suggested command");

  const showGreeting = forceGreeting ?? shouldShowGreeting(storage);
  if (showGreeting) {
    const greeting = document.createElement("p");
    greeting.className = "resume-card__greeting";
    greeting.textContent = `Welcome, ${data.user || "—"}.`;
    card.appendChild(greeting);
    markGreetingShown(storage);
  }

  const hereEyebrow = document.createElement("p");
  hereEyebrow.className = "resume-card__eyebrow resume-card__eyebrow--accent";
  hereEyebrow.textContent = "You are here:";
  card.appendChild(hereEyebrow);

  const breadcrumb = document.createElement("p");
  breadcrumb.className = "resume-card__breadcrumb";
  breadcrumb.textContent = formatBreadcrumb(data.breadcrumb || []);
  card.appendChild(breadcrumb);

  const nextEyebrow = document.createElement("p");
  nextEyebrow.className = "resume-card__eyebrow resume-card__eyebrow--mute";
  nextEyebrow.textContent = "Suggested next:";
  card.appendChild(nextEyebrow);

  const commandRow = document.createElement("div");
  commandRow.className = "resume-card__command-row";

  const commandGroup = document.createElement("div");
  commandGroup.className = "resume-card__command-group";
  commandGroup.setAttribute("role", "group");
  commandGroup.setAttribute("aria-label", "Suggested command, click to copy");

  const surface = document.createElement("div");
  surface.className = "inverted-command";

  const commandText = document.createElement("code");
  commandText.className = "inverted-command__text";
  commandText.textContent = normalizeCommand(data.command);

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-btn";
  copyButton.setAttribute("aria-label", COPY_ARIA_LABEL);
  copyButton.appendChild(createGlyph("copy", "copy-btn__glyph"));

  surface.append(commandText, copyButton);
  commandGroup.appendChild(surface);
  commandRow.appendChild(commandGroup);
  card.appendChild(commandRow);

  bindCopyButton(copyButton, data.command, liveRegion);

  const footer = document.createElement("freshness-footer");
  if (data.lastPoll != null) {
    footer.setAttribute("last-poll", String(data.lastPoll));
  }
  footer.setAttribute("variant", data.variant || "default");
  card.appendChild(footer);

  root.insertBefore(card, liveRegion);
}

export const SYNTHETIC_RESUME_FIXTURE = {
  user: "diep",
  breadcrumb: ["Epic 5", "Story 5.8", "Resume Card"],
  command: "sdlc status --suggested-next",
  lastPoll: "2026-06-25T14:32:05.000Z",
  variant: "default",
};

class ResumeCard extends HTMLElement {
  static get observedAttributes() {
    return ["user", "breadcrumb", "command", "last-poll", "variant", "show-greeting"];
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
    const showGreetingAttr = this.getAttribute("show-greeting");
    const forceGreeting =
      showGreetingAttr === "true" ? true : showGreetingAttr === "false" ? false : undefined;
    const breadcrumbAttr = this.getAttribute("breadcrumb");
    const breadcrumbParts = breadcrumbAttr
      ? parseBreadcrumb(breadcrumbAttr)
      : SYNTHETIC_RESUME_FIXTURE.breadcrumb;
    renderResumeCard(
      this,
      {
        user: this.getAttribute("user") || SYNTHETIC_RESUME_FIXTURE.user,
        breadcrumb: breadcrumbParts,
        command: this.getAttribute("command") || SYNTHETIC_RESUME_FIXTURE.command,
        lastPoll: this.getAttribute("last-poll") || SYNTHETIC_RESUME_FIXTURE.lastPoll,
        variant: this.getAttribute("variant") || SYNTHETIC_RESUME_FIXTURE.variant,
      },
      { forceGreeting },
    );
  }
}

if (!customElements.get("resume-card")) {
  customElements.define("resume-card", ResumeCard);
}

export {
  COPY_ARIA_LABEL,
  COPY_FEEDBACK_MS,
  COPY_LIVE_MESSAGE,
  GREETING_STORAGE_KEY,
  bindCopyButton,
  formatBreadcrumb,
  markGreetingShown,
  normalizeCommand,
  parseBreadcrumb,
  renderResumeCard,
  shouldShowGreeting,
  swapCopyGlyph,
};
