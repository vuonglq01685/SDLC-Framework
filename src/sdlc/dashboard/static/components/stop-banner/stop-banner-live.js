/**
 * STOP Banner live poller (Story 5.19 D1a).
 *
 * Reads the sticky `state.json` STOP slice via the masthead ETag/304 idiom,
 * maps to the banner view-model, and feeds `renderStopBanners` with
 * content-delta guarding (NFR-PERF-4).
 */

import { renderSectionBlockHeading } from "../section-heading/section-heading.js";
import {
  mapStateToTriggers,
  renderStopBanners,
  triggersSignature,
} from "./stop-banner.js";

const POLL_INTERVAL_MS = 3_000;

async function pollStateJson({ url = "/state.json", etagRef = { value: null }, fetchFn = fetch, signal } = {}) {
  const headers = etagRef.value ? { "If-None-Match": etagRef.value } : {};
  const response = await fetchFn(url, {
    headers,
    signal,
  });
  if (response.status === 304) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`state poll failed: ${response.status}`);
  }
  // Parse the body BEFORE committing the new ETag: if `response.json()` rejects
  // (a truncated/partial body on a flaky read), committing the ETag first would
  // make the next poll send `If-None-Match` for a version we never rendered —
  // the server answers 304 and the STOP slice freezes at last-good.
  const data = await response.json();
  const etag = response.headers.get("ETag");
  if (etag) {
    etagRef.value = etag;
  }
  return data;
}

function ensureAlertsColumn(root) {
  let column = root.querySelector(":scope > .alerts-col");
  if (!column) {
    column = document.createElement("div");
    column.className = "alerts-col";

    const headingHost = document.createElement("div");
    headingHost.className = "alerts-col__heading";
    column.appendChild(headingHost);

    const alertsHost = document.createElement("div");
    alertsHost.id = "alertsHost";
    alertsHost.className = "stop-banner-host";
    column.appendChild(alertsHost);

    root.replaceChildren(column);
  }
  return {
    column,
    headingHost: column.querySelector(".alerts-col__heading"),
    alertsHost: column.querySelector("#alertsHost"),
  };
}

function renderAlertsHeading(headingHost, count) {
  if (!headingHost) {
    return;
  }
  renderSectionBlockHeading(headingHost, { title: "Alerts", count });
}

/**
 * Start polling `/state.json` on a 3 s cycle for the STOP slice.
 * Mounts the alerts column shell when `host` is empty.
 */
export function startStopBannerLivePoller(host, opts = {}) {
  // Idempotent (re)start: tear down any poller already bound to this host so a
  // second call does not leak the previous setInterval (mirrors resume-card's
  // convention of stashing the dispose callback on the host).
  if (typeof host._stopPoller === "function") {
    host._stopPoller();
  }
  const { url = "/state.json", intervalMs = POLL_INTERVAL_MS, fetchFn = fetch, now = () => Date.now() } = opts;
  const { headingHost, alertsHost } = ensureAlertsColumn(host);

  let disposed = false;
  let inFlight = false;
  let controller = null;
  let lastSignature = null;
  const etagRef = { value: null };

  renderAlertsHeading(headingHost, 0);
  renderStopBanners(alertsHost, [], { variant: "loading" });

  const tick = async () => {
    if (inFlight || disposed) {
      return;
    }
    inFlight = true;
    controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    try {
      const json = await pollStateJson({
        url,
        etagRef,
        fetchFn,
        signal: controller ? controller.signal : undefined,
      });
      if (disposed) {
        return;
      }
      if (json == null) {
        return;
      }
      const triggers = mapStateToTriggers(json);
      const signature = triggersSignature(triggers);
      if (signature === lastSignature) {
        return;
      }
      lastSignature = signature;
      renderAlertsHeading(headingHost, triggers.length);
      renderStopBanners(alertsHost, triggers, {
        lastPoll: new Date(now()).toISOString(),
        timerHost: alertsHost,
      });
    } catch {
      // Keep last-known-good on transient failure or abort (5.20 owns disconnection).
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

export { POLL_INTERVAL_MS, ensureAlertsColumn, pollStateJson };
