/**
 * Page-wide connection-state broker (Story 5.20 / UX §7.11).
 *
 * Client-only pub/sub keyed off the canonical `/state.json` liveness poll.
 * Surfaces subscribe; the masthead poller reports poll outcomes.
 */

import { formatLocalTime } from "../freshness-footer/freshness-footer.js";

export const DISCONNECT_THRESHOLD = 3;

let state = "default";
let consecutiveFailures = 0;
const subscribers = new Set();

function notify() {
  subscribers.forEach((fn) => {
    try {
      fn(state);
    } catch {
      // Isolate a throwing subscriber: one surface's render error must not
      // abort notification of the other page-wide surfaces (§7.11 simultaneity),
      // nor propagate back through reportPollResult into the masthead poll tick
      // (which would report a spurious failure and bounce a just-recovered state).
    }
  });
}

/** @param {{ ok: boolean }} result */
function reportPollResult({ ok }) {
  if (ok) {
    consecutiveFailures = 0;
    if (state !== "default") {
      state = "default";
      notify();
    }
    return;
  }
  consecutiveFailures += 1;
  if (consecutiveFailures >= DISCONNECT_THRESHOLD && state !== "disconnected") {
    state = "disconnected";
    notify();
  }
}

/** @param {(next: "default" | "disconnected") => void} fn */
function subscribe(fn) {
  subscribers.add(fn);
  try {
    fn(state);
  } catch {
    // A throw during the immediate current-state delivery must not prevent
    // returning the dispose handle below (else the subscriber leaks forever).
  }
  return () => {
    subscribers.delete(fn);
  };
}

function getState() {
  return state;
}

/** Test-only reset — not used in production pollers. */
function _resetForTests() {
  state = "default";
  consecutiveFailures = 0;
}

/**
 * §7.11 honest-disconnection banner — reuses STOP-banner `.alert` treatment (AC3).
 * @param {HTMLElement} host
 * @param {{ lastPoll?: Date | string | number | null }} opts
 */
function renderHonestDisconnectionBanner(host, { lastPoll } = {}) {
  host.replaceChildren();

  const banner = document.createElement("article");
  banner.className = "stop-banner alert crit honest-disconnection-banner";
  banner.setAttribute("role", "alert");

  const title = document.createElement("p");
  title.className = "stop-banner__title a-title";
  title.textContent = "CRITICAL: Dashboard disconnected";

  const detail = document.createElement("p");
  detail.className = "stop-banner__detail a-detail";
  let timestamp = "--:--:--";
  if (lastPoll != null) {
    const date = lastPoll instanceof Date ? lastPoll : new Date(lastPoll);
    if (!Number.isNaN(date.getTime())) {
      timestamp = formatLocalTime(date);
    }
  }
  detail.textContent = `Dashboard cannot reach state. Last successful poll ${timestamp}.`;

  banner.append(title, detail);
  host.appendChild(banner);
}

/**
 * Broker-driven banner host wiring for fixtures / future page assembly (D2a).
 * @param {HTMLElement} host
 * @param {{ getLastPoll?: () => Date | null }} opts
 */
function bindHonestDisconnectionBanner(host, { getLastPoll = () => null } = {}) {
  return subscribe((brokerState) => {
    if (brokerState === "disconnected") {
      renderHonestDisconnectionBanner(host, { lastPoll: getLastPoll() });
    } else {
      host.replaceChildren();
    }
  });
}

export {
  bindHonestDisconnectionBanner,
  getState,
  renderHonestDisconnectionBanner,
  reportPollResult,
  subscribe,
  _resetForTests,
};
