/**
 * STOP Banner (Story 5.19 / UX §6.7).
 *
 * Renders Epic-4 STOP triggers with severity via `.alert` left-edge treatment
 * + mandatory text severity tag (never color-only). Keys off code `trigger_id`s
 * from engine/stop_registry.py — dashboard MUST NOT import the engine (D3).
 */

import "../empty-state/empty-state.js";
import "../freshness-footer/freshness-footer.js";
import { renderEmptyState, EMPTY_STATE_MESSAGE } from "../empty-state/empty-state.js";
import { createGlyph } from "../signoff-cell/signoff-cell.js";
import {
  bindCopyButton,
  normalizeCommand,
} from "../resume-card/resume-card.js";

const MAX_REASON_LEN = 200;
const COPY_ARIA_LABEL = "Copy suggested action";

/** Authoritative trigger→severity map (D3). Cross-check: stop_registry.py:17–34. */
export const TRIGGER_META = {
  high_risk_path: {
    severity: "crit",
    label: "High risk path",
    defaultAction: "sdlc trace --last-stop",
  },
  agent_failed: {
    severity: "crit",
    label: "Agent failed",
    defaultAction: "sdlc status",
  },
  open_clarification: {
    severity: "info",
    label: "Open clarification",
    defaultAction: "sdlc research",
  },
  signoff_required: {
    severity: "warn",
    label: "Signoff required",
    defaultAction: "sdlc signoff",
  },
  replan_dirty: {
    severity: "warn",
    label: "Replan dirty",
    defaultAction: "sdlc replan",
  },
  bug_awaiting_decide: {
    severity: "warn",
    label: "Bug awaiting decide",
    defaultAction: "sdlc decide",
  },
  pr_ready_story: {
    severity: "info",
    label: "PR ready story",
    defaultAction: "sdlc next",
  },
  watchdog_timeout: {
    severity: "crit",
    label: "Watchdog timeout",
    defaultAction: "sdlc status",
  },
  agent_failure_after_retries: {
    severity: "crit",
    label: "Agent failure after retries",
    defaultAction: "sdlc status",
  },
};

const SEVERITY_TAG = {
  crit: "CRITICAL:",
  warn: "WARNING:",
  info: "INFO:",
  // Review 2026-07-07 (Decision a): a neutral/unknown-severity banner still
  // carries a text tag so it is never color-only and is never mislabeled as a
  // real severity.
  neutral: "NOTICE:",
};

const NEUTRAL_META = {
  severity: "neutral",
  label: "Unknown stop",
  defaultAction: "",
};

const KNOWN_TRIGGER_IDS = new Set(Object.keys(TRIGGER_META));

// Document-unique title ids so `aria-labelledby` never collides when more than
// one banner host renders on the same page (a synthetic <stop-banner-host>
// alongside the live #alertsHost) — a per-host index alone is not page-unique.
let _bannerTitleSeq = 0;

const CONTROL_CHAR_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;
const NEWLINE_RE = /[\n\r\u000b\u000c\u0085\u2028\u2029]+/g;

/** D4: sanitize untrusted reason/summary strings at the client edge. */
export function sanitizeReason(raw) {
  if (raw == null) {
    return "";
  }
  let text = String(raw).replace(CONTROL_CHAR_RE, " ").replace(NEWLINE_RE, " ").trim();
  if (text.length > MAX_REASON_LEN) {
    text = `${text.slice(0, MAX_REASON_LEN)}…`;
  }
  return text;
}

function resolveMeta(triggerId) {
  const key = triggerId == null ? "" : String(triggerId).trim();
  if (key && Object.prototype.hasOwnProperty.call(TRIGGER_META, key)) {
    return TRIGGER_META[key];
  }
  return { ...NEUTRAL_META, label: key || NEUTRAL_META.label };
}

function roleForSeverity(severity) {
  return severity === "crit" ? "alert" : "status";
}

function createSeverityDot(severity) {
  if (severity === "neutral") {
    return null;
  }
  const dot = document.createElement("span");
  dot.className = "stop-banner__severity-dot live-dot-pulse--stop";
  dot.setAttribute("aria-hidden", "true");
  dot.dataset.severity = severity;
  return dot;
}

function createActionRow(actionText, liveRegion, timerHost) {
  const row = document.createElement("div");
  row.className = "stop-banner__action a-action";

  const normalized = normalizeCommand(actionText);
  if (!normalized) {
    return row;
  }

  const surface = document.createElement("div");
  surface.className = "inverted-command";

  const commandText = document.createElement("code");
  commandText.className = "inverted-command__text";
  commandText.textContent = normalized;
  commandText.setAttribute("tabindex", "-1");

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-btn";
  copyButton.setAttribute("aria-label", COPY_ARIA_LABEL);
  copyButton.appendChild(createGlyph("copy", "copy-btn__glyph"));

  surface.append(commandText, copyButton);
  row.appendChild(surface);
  bindCopyButton(copyButton, actionText, liveRegion, { timerHost });
  return row;
}

function createStopBannerElement(trigger, { liveRegion, timerHost } = {}) {
  const triggerId = trigger && trigger.triggerId;
  const meta = resolveMeta(triggerId);
  const severity = meta.severity;
  const severityTag = SEVERITY_TAG[severity] || "";

  const banner = document.createElement("article");
  banner.className = `stop-banner alert ${severity !== "neutral" ? severity : ""}`.trim();
  banner.setAttribute("role", roleForSeverity(severity));

  _bannerTitleSeq += 1;
  const titleId = `stop-banner-title-${_bannerTitleSeq}`;
  banner.setAttribute("aria-labelledby", titleId);

  const title = document.createElement("p");
  title.className = "stop-banner__title a-title";
  title.id = titleId;
  const titleParts = [severityTag, meta.label].filter(Boolean);
  title.textContent = titleParts.join(" ").trim();

  const detail = document.createElement("p");
  detail.className = "stop-banner__detail a-detail";
  const targetId = trigger && trigger.targetId;
  const reason = sanitizeReason(trigger && trigger.reason);
  const detailParts = [];
  if (targetId) {
    detailParts.push(`Target: ${sanitizeReason(targetId)}`);
  }
  if (reason) {
    detailParts.push(reason);
  }
  if (!detailParts.length && triggerId && !KNOWN_TRIGGER_IDS.has(String(triggerId))) {
    detailParts.push(sanitizeReason(triggerId));
  }
  detail.textContent = detailParts.join(" — ") || "—";

  const dot = createSeverityDot(severity);
  banner.append(title, detail);
  if (dot) {
    banner.insertBefore(dot, title);
  }

  const actionText =
    (trigger && trigger.action) || meta.defaultAction || "";
  const actionRow = createActionRow(actionText, liveRegion, timerHost);
  if (actionRow.childElementCount > 0) {
    banner.appendChild(actionRow);
  }

  return banner;
}

function ensureLiveRegion(host) {
  let region = host.querySelector(":scope > .stop-banner-host__live-region");
  if (!region) {
    region = document.createElement("div");
    region.className = "stop-banner-host__live-region stop-banner-host__sr-only";
    region.setAttribute("aria-live", "polite");
    region.setAttribute("aria-atomic", "true");
    host.appendChild(region);
  }
  return region;
}

/**
 * Render STOP banners into `host` (typically `#alertsHost`).
 * Empty trigger list → Empty State (AC3) with embedded freshness footer.
 */
export function renderStopBanners(
  host,
  triggers = [],
  { lastPoll, variant = "default", nowMs, timerHost } = {},
) {
  const list = Array.isArray(triggers) ? triggers : [];
  host.replaceChildren();

  if (!list.length) {
    renderEmptyState(host, {
      message: EMPTY_STATE_MESSAGE,
      lastPoll,
      variant,
      nowMs,
    });
    return;
  }

  // Create the sr-only live region AFTER clearing the host so it stays attached
  // for this render — copy buttons announce into it on click, and the previous
  // order (append region, then replaceChildren) detached it, silently dropping
  // every "copied to clipboard" announcement.
  const liveRegion = ensureLiveRegion(host);

  list.forEach((trigger) => {
    host.appendChild(
      createStopBannerElement(trigger, {
        liveRegion,
        timerHost: timerHost || host,
      }),
    );
  });

  const footer = document.createElement("freshness-footer");
  if (lastPoll != null) {
    footer.setAttribute("last-poll", String(lastPoll));
  }
  if (nowMs != null) {
    footer.setAttribute("now", String(nowMs));
  }
  footer.setAttribute("variant", variant);
  host.appendChild(footer);
}

/** Synthetic fixture: all 7 registry trigger_ids (AC1 rendering capability). */
export function buildSyntheticAll7Triggers() {
  return [
    {
      triggerId: "high_risk_path",
      targetId: "src/sdlc/engine/dispatch.py",
      reason: "High-risk path detected in auto loop",
      action: "sdlc trace --last-stop",
    },
    {
      triggerId: "agent_failed",
      targetId: "5-19-stop-banner",
      reason: "Agent failed after retries",
      action: "sdlc status",
    },
    {
      triggerId: "open_clarification",
      targetId: "clarification-001",
      reason: "Open clarification awaiting human input",
      action: "sdlc research",
    },
    {
      triggerId: "signoff_required",
      targetId: "phase-2",
      reason: "Signoff required before continuing",
      action: "sdlc signoff",
    },
    {
      triggerId: "replan_dirty",
      targetId: "epic-5",
      reason: "Replan dirty items need reconciliation",
      action: "sdlc replan",
    },
    {
      triggerId: "bug_awaiting_decide",
      targetId: "BUG-42",
      reason: "Bug ticket awaiting decide verb",
      action: "sdlc decide",
    },
    {
      triggerId: "pr_ready_story",
      targetId: "5-18-resume-card",
      reason: "Story ready for PR",
      action: "sdlc next",
    },
  ];
}

export const SYNTHETIC_ALL7_FIXTURE = {
  triggers: buildSyntheticAll7Triggers(),
};

/** Map sticky-halt state.json slice → banner view-model (D1a: single active trigger). */
export function mapStateToTriggers(state) {
  if (!state || state.auto_loop_status !== "halted") {
    return [];
  }
  const triggerId = state.stop_reason;
  if (!triggerId) {
    return [];
  }
  const meta = resolveMeta(triggerId);
  return [
    {
      triggerId,
      targetId: triggerId,
      action: meta.defaultAction,
    },
  ];
}

export function triggersSignature(triggers) {
  return JSON.stringify(
    (triggers || []).map((t) => [
      t && t.triggerId,
      t && t.targetId,
      t && t.reason,
      t && t.action,
    ]),
  );
}

class StopBannerHost extends HTMLElement {
  connectedCallback() {
    if (this.dataset.source === "live") {
      return;
    }
    renderStopBanners(this, SYNTHETIC_ALL7_FIXTURE.triggers);
  }
}

if (!customElements.get("stop-banner-host")) {
  customElements.define("stop-banner-host", StopBannerHost);
}

export {
  KNOWN_TRIGGER_IDS,
  MAX_REASON_LEN,
  NEUTRAL_META,
  SEVERITY_TAG,
  createStopBannerElement,
  resolveMeta,
};
