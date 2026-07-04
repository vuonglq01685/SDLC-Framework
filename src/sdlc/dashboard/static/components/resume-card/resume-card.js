/**
 * <resume-card> custom element (Story 5.8 shell; real-data hardening Story 5.18).
 */

import "../freshness-footer/freshness-footer.js";
import { createGlyph } from "../signoff-cell/signoff-cell.js";

const GREETING_STORAGE_KEY = "sdlc.resume-card.greetingShown";
const COPY_FEEDBACK_MS = 1_000;
const COPY_ARIA_LABEL = "Copy suggested command";
const COPY_LIVE_MESSAGE = "copied to clipboard";
const SHELL_PREFIX_RE = /^[$>❯]\s*/u;
// D5 (folds 5.8 DEF-1): the real suggested_next_command is untrusted state
// content -- collapse ANY interior line separator plus its surrounding
// whitespace to a single space so the copyable string is always single-line.
// Covers \n, a lone \r (treated as Enter by most terminals), \r\n, vertical
// tab, form feed, NEL, and the Unicode line/paragraph separators -- an
// unhardened multi-line value would otherwise paste-and-auto-execute up to the
// first line break.
const INTERIOR_NEWLINE_RE = /\s*[\n\r\u000b\u000c\u0085\u2028\u2029]\s*/gu;

function normalizeCommand(raw) {
  if (raw == null) {
    return "";
  }
  let text = String(raw).trim();
  text = text.replace(SHELL_PREFIX_RE, "");
  text = text.replace(INTERIOR_NEWLINE_RE, " ");
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

function bindCopyButton(
  button,
  command,
  liveRegion,
  { clipboard = navigator.clipboard, feedbackMs = COPY_FEEDBACK_MS, timerHost } = {},
) {
  // DEF-8: the reset timer is stashed on `timerHost` (a PERSISTENT node across
  // renders -- normally the custom-element instance itself), not a plain
  // closure variable, so a caller with access to the same host (a re-render,
  // or disconnectedCallback) can find and cancel a still-pending timer left
  // over from a previous bind. Falls back to the button itself when no host
  // is supplied (kept working for direct renderResumeCard(root, data) callers
  // that don't pass timerHost).
  const host = timerHost || button;
  button.addEventListener("click", async () => {
    const normalized = normalizeCommand(command);
    if (!normalized) {
      // P5 (review): nothing to copy (e.g. the neutral loading state's empty
      // command). Do not fire a false "copied" confirmation or icon swap.
      return;
    }
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
    if (host._copyResetHandle != null) {
      window.clearTimeout(host._copyResetHandle);
    }
    host._copyResetHandle = window.setTimeout(() => {
      swapCopyGlyph(button, "copy");
      host._copyResetHandle = null;
    }, feedbackMs);
  });
}

function renderResumeCard(
  root,
  data,
  { storage = sessionStorage, forceGreeting, timerHost, trackAnnounce = true } = {},
) {
  const liveRegion = ensureLiveRegion(root);
  root.querySelectorAll(":scope > .resume-card").forEach((node) => node.remove());

  const card = document.createElement("section");
  card.className = "resume-card";
  card.setAttribute("role", "region");
  card.setAttribute("aria-label", "Resume position and suggested command");

  // P8 (resolves review DN-2): only greet when a real user name is present. The
  // live /api/resume token carries no `user` field, so an unguarded greeting
  // would paint the em-dash placeholder AND burn the once-per-session
  // sessionStorage flag on it. Suppress it (and do NOT mark the flag) when there
  // is no real user -- the attribute/synthetic path always has one, so it stays
  // unaffected.
  const hasUser = typeof data.user === "string" && data.user.trim() !== "";
  const showGreeting = (forceGreeting ?? shouldShowGreeting(storage)) && hasUser;
  if (showGreeting) {
    const greeting = document.createElement("p");
    greeting.className = "resume-card__greeting";
    greeting.textContent = `Welcome, ${data.user}.`;
    card.appendChild(greeting);
    markGreetingShown(storage);
  }

  const hereEyebrow = document.createElement("p");
  hereEyebrow.className = "resume-card__eyebrow resume-card__eyebrow--accent";
  hereEyebrow.textContent = "You are here:";
  card.appendChild(hereEyebrow);

  // P6 (review): coerce breadcrumb parts on BOTH the attribute and live paths
  // (parseBreadcrumb trims + drops empty/non-string parts) so a stray empty or
  // non-string part never renders as " /  / " or "[object Object]". Idempotent
  // on the already-clean attribute-path array.
  const breadcrumbText = formatBreadcrumb(parseBreadcrumb(data.breadcrumb || []));
  const breadcrumb = document.createElement("p");
  breadcrumb.className = "resume-card__breadcrumb";
  breadcrumb.textContent = breadcrumbText;
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

  const normalizedCommand = normalizeCommand(data.command);
  const commandText = document.createElement("code");
  commandText.className = "inverted-command__text";
  commandText.textContent = normalizedCommand;

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-btn";
  copyButton.setAttribute("aria-label", COPY_ARIA_LABEL);
  copyButton.appendChild(createGlyph("copy", "copy-btn__glyph"));

  surface.append(commandText, copyButton);
  commandGroup.appendChild(surface);
  commandRow.appendChild(commandGroup);
  card.appendChild(commandRow);

  bindCopyButton(copyButton, data.command, liveRegion, { timerHost: timerHost || root });

  const footer = document.createElement("freshness-footer");
  if (data.lastPoll != null) {
    footer.setAttribute("last-poll", String(data.lastPoll));
  }
  footer.setAttribute("variant", data.variant || "default");
  card.appendChild(footer);

  root.insertBefore(card, liveRegion);

  // DEF-5: announce poll-driven breadcrumb/command CHANGES through the SAME
  // persistent live region used for copy feedback. A poll re-render fully
  // replaces the `.resume-card` subtree above (the frozen 5.8 render
  // strategy), so a naive `aria-live` wrapper around the visible breadcrumb/
  // command would itself be torn down and recreated every render and is not
  // reliably announced by assistive tech; this reused, never-replaced region
  // is. Only announces on an actual CHANGE (never the first mount) so a
  // steady-state 3 s poll does not spam identical announcements.
  //
  // P4 (review): the neutral loading render passes `trackAnnounce: false` so it
  // does NOT seed the baseline below -- otherwise the loading -> first-real-data
  // transition reads as a "change" and spuriously announces "Updated —" on the
  // very first content paint.
  if (trackAnnounce) {
    const previous = root._resumeCardAnnounced;
    const changed =
      previous != null &&
      (previous.breadcrumb !== breadcrumbText || previous.command !== normalizedCommand);
    if (changed) {
      liveRegion.textContent = `Updated — ${breadcrumbText}. Suggested next: ${normalizedCommand}`;
    }
    root._resumeCardAnnounced = { breadcrumb: breadcrumbText, command: normalizedCommand };
  }
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
    // A host marked `data-source="live"` (set in markup BEFORE this element
    // upgrades, e.g. resume-card-live.fixture.html) is driven exclusively by
    // `startResumeCardLivePoller` (external wiring, mirrors activity-feed's
    // convention) — auto-rendering the synthetic/attribute fixture here first
    // would flash stale content before the real poll lands.
    if (this.dataset.source === "live") {
      return;
    }
    this._scheduleRender();
  }

  disconnectedCallback() {
    if (this._copyResetHandle != null) {
      window.clearTimeout(this._copyResetHandle);
      this._copyResetHandle = null;
    }
    // Generic convention (mirrors host._fixtureRef elsewhere): whoever started
    // a live poller against this host (resume-card-live.js) stashes its
    // dispose callback here, so the poller's AbortController is aborted at
    // the exact moment of disconnection — no import of the live-poller
    // module needed from this file (one-directional dependency, matches the
    // backlog-tree.js / backlog-tree-live.js split).
    if (typeof this._stopPoller === "function") {
      this._stopPoller();
      this._stopPoller = null;
    }
  }

  attributeChangedCallback() {
    if (this.isConnected) {
      this._scheduleRender();
    }
  }

  // DEF-8: coalesce a synchronous burst of attribute changes (custom-element
  // upgrade delivers one attributeChangedCallback per observed attribute,
  // all before connectedCallback) into a SINGLE microtask-scheduled _render()
  // — otherwise render #1 shows the once-per-session greeting and burns the
  // sessionStorage flag, then render #2 (moments later, same tick) rebuilds
  // WITHOUT the greeting (flag now set) and the user never sees it painted.
  _scheduleRender() {
    if (this._renderPending) {
      return;
    }
    this._renderPending = true;
    queueMicrotask(() => {
      this._renderPending = false;
      if (this.isConnected) {
        this._render();
      }
    });
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
      { forceGreeting, timerHost: this },
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
