import "../live-dot/live-dot.js";
import { formatLocalTime } from "../freshness-footer/freshness-footer.js";

const POLL_INTERVAL_MS = 3_000;
const ARIA_LIVE_INTERVAL_MS = 60_000;
const SEPARATOR = "\u00b7";

function resolveConnectionVariant(raw) {
  const key = String(raw || "default").trim().toLowerCase();
  return key === "warn" || key === "disconnected" ? key : "default";
}

function formatTabTitle(projectName, phaseNumber, progressPercent) {
  return `${projectName} ${SEPARATOR} Phase ${phaseNumber} ${progressPercent}%`;
}

function variantAnnouncementText(variantKey) {
  const labels = { default: "Connected", warn: "Connection warning", disconnected: "Disconnected" };
  return labels[variantKey] || labels.default;
}

function createAriaLiveRateLimiter({ now = () => Date.now(), intervalMs = ARIA_LIVE_INTERVAL_MS } = {}) {
  let lastAnnouncedAt = -Infinity;
  let lastVariant = null;
  return {
    onVariantChange(variant) {
      const normalized = resolveConnectionVariant(variant);
      if (normalized === lastVariant) return null;
      const nowMs = now();
      const hadPriorVariant = lastVariant !== null;
      // Suppress within the rate-limit window WITHOUT advancing lastVariant, so the
      // current (still-unannounced) variant is re-detected on a later change and
      // announced once the window opens — otherwise a change suppressed here is
      // swallowed forever and a screen-reader user is never told the state changed.
      if (hadPriorVariant && nowMs - lastAnnouncedAt < intervalMs) return null;
      lastVariant = normalized;
      lastAnnouncedAt = nowMs;
      return variantAnnouncementText(normalized);
    },
  };
}

function parseLastPoll(raw) {
  if (raw == null || raw === "") return null;
  const numeric = Number(raw);
  if (!Number.isNaN(numeric) && Number.isFinite(numeric)) {
    const fromNumeric = new Date(numeric);
    return Number.isNaN(fromNumeric.getTime()) ? null : fromNumeric;
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatMastheadSubLine({ projectName, owner, lastPoll, disconnected }) {
  const timestamp = lastPoll ? formatLocalTime(lastPoll) : "--:--:--";
  if (disconnected) return `DISCONNECTED ${SEPARATOR} LAST POLL ${timestamp}`;
  return `${projectName} ${SEPARATOR} ${owner} ${SEPARATOR} UPDATED ${timestamp}`;
}

function toNumberOr(value, fallback) {
  if (value == null || value === "") return fallback;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function mapStateFromJson(json, { port, lastPoll = new Date() } = {}) {
  const connectionVariant = resolveConnectionVariant(json.connection_variant || json.connectionVariant);
  return {
    projectName: json.project_name || json.projectName || "Unknown Project",
    owner: json.owner || "—",
    phase: toNumberOr(json.phase, 1),
    progress: toNumberOr(json.progress ?? json.progress_percent, 0),
    connectionVariant,
    port: port ?? json.port ?? "—",
    lastPoll,
    disconnected: connectionVariant === "disconnected",
  };
}

async function pollStateJson({ url = "/state.json", etagRef = { value: null }, fetchFn = fetch } = {}) {
  const headers = etagRef.value ? { "If-None-Match": etagRef.value } : {};
  const response = await fetchFn(url, { headers });
  if (response.status === 304) return null;
  if (!response.ok) throw new Error(`state poll failed: ${response.status}`);
  const etag = response.headers.get("ETag");
  if (etag) etagRef.value = etag;
  return response.json();
}

function ensureLiveRegion(root) {
  let region = root.querySelector(":scope > .masthead__live-region");
  if (!region) {
    region = document.createElement("div");
    region.className = "masthead__live-region masthead__sr-only";
    region.setAttribute("aria-live", "polite");
    region.setAttribute("aria-atomic", "true");
    root.appendChild(region);
  }
  return region;
}

function renderMasthead(root, state, { rateLimiter, updateTitle = false } = {}) {
  const { projectName, owner, phase, progress, connectionVariant, port, lastPoll, disconnected } = state;
  // Persistent polite live region — created once and reused so screen readers
  // reliably announce connection-state changes. A region recreated on every render
  // is treated as initial state and is not announced.
  const liveRegion = ensureLiveRegion(root);
  const previousBanner = root.querySelector(":scope > header");
  if (previousBanner) previousBanner.remove();
  const banner = document.createElement("header");
  banner.setAttribute("role", "banner");
  const inner = document.createElement("div");
  inner.className = "masthead__inner";
  const main = document.createElement("div");
  main.className = "masthead__main";
  const heading = document.createElement("h1");
  heading.className = "masthead__title";
  const projectSpan = document.createElement("span");
  projectSpan.className = "masthead__project";
  projectSpan.textContent = projectName;
  const arrowSpan = document.createElement("span");
  arrowSpan.className = "masthead__arrow";
  arrowSpan.setAttribute("aria-hidden", "true");
  arrowSpan.textContent = "→";
  const phaseSpan = document.createElement("span");
  phaseSpan.className = "masthead__phase";
  phaseSpan.textContent = `Phase ${phase}`;
  heading.append(projectSpan, arrowSpan, phaseSpan);
  const sub = document.createElement("p");
  sub.className = "masthead__sub";
  sub.textContent = formatMastheadSubLine({ projectName, owner, lastPoll, disconnected });
  main.append(heading, sub);
  const rail = document.createElement("div");
  rail.className = "masthead__rail";
  const portLine = document.createElement("span");
  portLine.className = "masthead__port";
  portLine.textContent = `PORT ${port}`;
  const live = document.createElement("div");
  live.className = "masthead__live";
  const dot = document.createElement("live-dot");
  dot.setAttribute("variant", connectionVariant);
  live.appendChild(dot);
  rail.append(portLine, live);
  inner.append(main, rail);
  banner.appendChild(inner);
  root.insertBefore(banner, liveRegion);
  if (rateLimiter) {
    const announcement = rateLimiter.onVariantChange(connectionVariant);
    if (announcement) liveRegion.textContent = announcement;
  }
  // Only the poller owns the browser tab title (Decision E2 / AC3). Static and
  // non-poll instances must not clobber document.title.
  if (updateTitle) {
    document.title = formatTabTitle(projectName, phase, progress);
  }
}

function startMastheadPoller(root, opts = {}) {
  const { url = "/state.json", port, intervalMs = POLL_INTERVAL_MS, fetchFn = fetch, now = () => Date.now() } = opts;
  const etagRef = { value: null };
  const rateLimiter = createAriaLiveRateLimiter({ now });
  const tick = async () => {
    try {
      const json = await pollStateJson({ url, etagRef, fetchFn });
      if (json == null) return;
      renderMasthead(root, mapStateFromJson(json, { port, lastPoll: new Date(now()) }), {
        rateLimiter,
        updateTitle: true,
      });
    } catch {
      // Keep the last-known-good render on a transient poll failure. Real
      // disconnection detection (≥3 consecutive failures → page-wide disconnected)
      // is Story 5.20's responsibility — 5.6 anti-scope. The disconnected visual is
      // driven only by the synthetic fixture flag, never synthesized on error.
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);
  return () => window.clearInterval(handle);
}

function buildStaticState(el) {
  const variant = resolveConnectionVariant(el.getAttribute("variant"));
  return mapStateFromJson({
    project_name: el.getAttribute("project-name"),
    owner: el.getAttribute("owner"),
    phase: el.getAttribute("phase"),
    progress: el.getAttribute("progress"),
    connection_variant: variant,
    port: el.getAttribute("port"),
  }, { lastPoll: parseLastPoll(el.getAttribute("last-poll")) || new Date() });
}

class SdlcMasthead extends HTMLElement {
  connectedCallback() {
    if (this.getAttribute("poll") === "true") {
      this._stopPoller = startMastheadPoller(this, { port: window.location.port || "—" });
      return;
    }
    renderMasthead(this, buildStaticState(this), { rateLimiter: createAriaLiveRateLimiter() });
  }
  disconnectedCallback() {
    if (typeof this._stopPoller === "function") this._stopPoller();
  }
}


if (!customElements.get("sdlc-masthead")) customElements.define("sdlc-masthead", SdlcMasthead);
export { formatTabTitle, createAriaLiveRateLimiter, POLL_INTERVAL_MS, renderMasthead, startMastheadPoller };
export { formatMastheadSubLine, mapStateFromJson, pollStateJson, resolveConnectionVariant, variantAnnouncementText, ARIA_LIVE_INTERVAL_MS };
export const SYNTHETIC_MASTHEAD_FIXTURE = { projectName: "SDLC-Framework", owner: "diep", phase: 2, progress: 45, connectionVariant: "default", port: 3847 };
