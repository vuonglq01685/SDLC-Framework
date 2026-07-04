/**
 * Resume Card real-data poller (Story 5.18 D1/D2/D4; masthead DEF-1/DEF-3 fold).
 *
 * Fetches the server-computed `/api/resume` envelope
 * (dashboard/routes/resume.py D1(b): phase, cursor {epic_id, story_id,
 * task_id, stage, breadcrumb}, suggested_next_command, state_hash) and feeds
 * it through the UNTOUCHED `renderResumeCard` seam (Story 5.8) — the
 * render/keyboard/a11y internals in resume-card.js stay exactly as frozen;
 * only the data source changes.
 *
 * D4 poll wiring: an INDEPENDENT poller (own 3 s interval, own `/api/resume`
 * fetch) mirrors the established batch-1 precedent
 * (`activity-feed.js::startActivityFeedLivePoller`,
 * `backlog-tree-live.js::startBacklogTreeLivePoller`) rather than literally
 * sharing masthead's `/state.json` timer instance — the resume card polls a
 * DIFFERENT endpoint with a different payload shape, so a single shared
 * fetch call is not a clean fit; the interval constant and the
 * guard/AbortController hardening below are kept consistent with those
 * siblings (5.16 shipped this exact deviation from its own story's literal
 * "reuse the shared poll" wording).
 *
 * Masthead DEF-1 fold: an in-flight re-entrancy guard (skip a tick while one
 * is pending) PLUS a real `AbortController` aborted on disconnect — masthead
 * itself only has the boolean-guard half of this; this is the first real
 * consumer to add the AbortController half.
 *
 * Masthead DEF-3 fold: render a neutral "Loading…" state on connect, before
 * the first poll resolves, so an early no-op response never leaves the card
 * blank.
 */

import { renderResumeCard } from "./resume-card.js";

const POLL_INTERVAL_MS = 3_000;

const LOADING_FIXTURE = {
  user: undefined,
  breadcrumb: ["Loading…"],
  command: "",
  lastPoll: null,
  variant: "loading",
};

/** Map one `/api/resume` envelope onto the renderer's field contract. */
function mapResumeToken(token) {
  const cursor = (token && token.cursor) || {};
  const breadcrumb = Array.isArray(cursor.breadcrumb)
    ? cursor.breadcrumb
    : [`Phase ${(token && token.phase) ?? 0}`];
  return {
    breadcrumb,
    command: (token && token.suggested_next_command) || "",
    lastPoll: new Date().toISOString(),
    variant: "default",
  };
}

/**
 * P3 (review): when a poll returns UNCHANGED content, refresh only the freshness
 * footer's timestamp in place -- keeps live data from looking frozen without
 * tearing down and rebuilding the whole card (which would drop copy-button focus
 * and clobber in-progress copy feedback).
 */
function refreshFreshnessTimestamp(host, lastPoll) {
  if (lastPoll == null) {
    return;
  }
  const footer = host.querySelector(".resume-card > freshness-footer");
  if (footer) {
    footer.setAttribute("last-poll", String(lastPoll));
  }
}

async function pollResumeSnapshot({ url = "/api/resume", fetchFn = fetch, signal } = {}) {
  const response = await fetchFn(url, signal ? { signal } : undefined);
  if (!response.ok) {
    throw new Error(`resume poll failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Start polling `/api/resume` on a 3 s cycle, feeding mapped tokens into the
 * untouched `renderResumeCard` seam. Renders a neutral loading state
 * immediately (DEF-3), then returns a dispose function that stops the timer
 * and aborts any in-flight request — also stashed on `host._stopPoller` so
 * `resume-card.js`'s own `disconnectedCallback` invokes it automatically
 * (generic convention, no import cycle back into this file).
 */
export function startResumeCardLivePoller(host, opts = {}) {
  const { url = "/api/resume", intervalMs = POLL_INTERVAL_MS, fetchFn = fetch } = opts;
  let disposed = false;
  let inFlight = false;
  let controller = null;
  // P3 (review): remember the last rendered content so a steady-state poll with
  // an unchanged token does NOT tear down and rebuild the card (which drops
  // copy-button focus and clobbers the in-progress copy->check feedback).
  let lastSignature = null;

  renderResumeCard(host, LOADING_FIXTURE, {
    forceGreeting: false,
    timerHost: host,
    trackAnnounce: false,
  });

  const tick = async () => {
    if (inFlight || disposed) {
      return;
    }
    inFlight = true;
    controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    try {
      const token = await pollResumeSnapshot({
        url,
        fetchFn,
        signal: controller ? controller.signal : undefined,
      });
      if (!disposed) {
        const mapped = mapResumeToken(token);
        const signature = JSON.stringify([mapped.breadcrumb, mapped.command]);
        if (signature === lastSignature) {
          // Unchanged content: refresh only the freshness footer timestamp in
          // place, never rebuild the card (preserves focus + copy feedback).
          refreshFreshnessTimestamp(host, mapped.lastPoll);
        } else {
          lastSignature = signature;
          renderResumeCard(host, mapped, { timerHost: host });
        }
      }
    } catch {
      // Keep the last-known-good render on a transient poll failure OR an
      // aborted in-flight request (mirrors activity-feed.js / masthead.js's
      // tick catch) — an abort must never surface as a visible error state.
    } finally {
      inFlight = false;
      controller = null;
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);

  const dispose = () => {
    disposed = true;
    window.clearInterval(handle);
    if (controller) {
      controller.abort();
    }
  };
  host._stopPoller = dispose;
  return dispose;
}

export { LOADING_FIXTURE, mapResumeToken, pollResumeSnapshot };
