/**
 * Phase Tracker real-signoff poller (Story 5.14 D1/D4).
 *
 * NOT a new custom element and NOT a rebuild of the frozen 5.9 phase-tracker
 * substrate (phase-tracker.js / signoff-cell.js / phase-item-row.js stay
 * untouched). This is a small plain-script poller — mirrors
 * `masthead.js` `startMastheadPoller` (setInterval(tick, 3000)) — that reads
 * the Task-1 `/api/signoff` seam and drives **attribute swaps** on the
 * existing `<signoff-cell data-phase="N">` / `<phase-item-row data-phase="N">`
 * elements the host page authors. Content-delta only (DD-06): a cell's
 * `state` attribute is written ONLY when it actually changed, and the grid
 * itself is never replaced/resynthesized — only-changed re-render (NFR-PERF-4).
 *
 * D2 click-through: an inline disclosure `[data-role="replan-detail"]`
 * region (plain `<div>`, NOT a `<dialog>`/modal/toast — §7.12 forbidden)
 * toggles open on clicking an `invalidated-by-replan` signoff-cell, showing
 * the persisted replan reason + downstream artifact list read through the
 * `/api/signoff` seam (which itself reads via `journal`/`signoff`, never
 * `engine` — module boundary).
 */

const POLL_INTERVAL_MS = 3_000;
const INVALIDATED_STATE = "invalidated-by-replan";

function mappedElements(root, phase) {
  return {
    signoffCell: root.querySelector(`signoff-cell[data-phase="${phase}"]`),
    itemRow: root.querySelector(`phase-item-row[data-phase="${phase}"]`),
    detail: root.querySelector(`[data-role="replan-detail"][data-phase="${phase}"]`),
  };
}

function setStateIfChanged(el, stateKey) {
  if (!el || !stateKey) return false;
  if (el.getAttribute("state") === stateKey) return false;
  el.setAttribute("state", stateKey);
  return true;
}

function renderReplanDetail(detailEl, entry) {
  if (!detailEl) return;
  const isInvalidated = Boolean(entry) && entry.state === INVALIDATED_STATE;
  if (!isInvalidated) {
    detailEl.hidden = true;
    detailEl.removeAttribute("data-opened");
    detailEl.removeAttribute("data-content-key");
    detailEl.replaceChildren();
    return;
  }
  const replan = entry.replan;
  const reasonText =
    (replan && replan.reason) || entry.invalidated_reason || "Invalidated by replan.";
  const downstream = (replan && replan.downstream_artifacts) || [];

  // Content-delta on the (small) detail subtree only — never touches the grid.
  // Rebuild ONLY when the reason/downstream actually changed: an OPEN disclosure
  // must survive a 3 s poll intact — a blind replaceChildren() every poll wipes
  // the user's in-progress text selection in the panel. Mirrors setStateIfChanged
  // for the cells (DD-06 / NFR-PERF-4 content-delta, applied to the detail region).
  const contentKey = JSON.stringify([reasonText, downstream]);
  if (detailEl.getAttribute("data-content-key") !== contentKey) {
    const reasonEl = document.createElement("p");
    reasonEl.className = "phase-tracker__replan-reason";
    reasonEl.textContent = reasonText;
    detailEl.replaceChildren(reasonEl);

    if (downstream.length > 0) {
      const list = document.createElement("ul");
      list.className = "phase-tracker__replan-downstream";
      for (const path of downstream) {
        const li = document.createElement("li");
        li.textContent = path;
        list.appendChild(li);
      }
      detailEl.appendChild(list);
    }
    detailEl.setAttribute("data-content-key", contentKey);
  }

  // A poll re-render never auto-opens the disclosure (D2: click-through
  // only); once the user HAS opened it, a poll refresh keeps it open so the
  // content update stays visible instead of yanking it shut mid-read.
  if (detailEl.getAttribute("data-opened") !== "true") {
    detailEl.hidden = true;
  }
}

function applySignoffSnapshot(root, snapshot) {
  const phases = (snapshot && snapshot.phases) || {};
  let changed = false;
  for (const phase of [1, 2, 3]) {
    const entry = phases[String(phase)];
    if (!entry) continue;
    const { signoffCell, itemRow, detail } = mappedElements(root, phase);
    if (setStateIfChanged(signoffCell, entry.state)) changed = true;
    if (setStateIfChanged(itemRow, entry.state)) changed = true;
    renderReplanDetail(detail, entry);
  }
  return changed;
}

function wireClickThrough(root, signal) {
  root.addEventListener(
    "click",
    (event) => {
      const cell =
        typeof event.target.closest === "function"
          ? event.target.closest("signoff-cell[data-phase]")
          : null;
      if (!cell) return;
      if (cell.getAttribute("state") !== INVALIDATED_STATE) return;
      const phase = cell.getAttribute("data-phase");
      const detail = root.querySelector(`[data-role="replan-detail"][data-phase="${phase}"]`);
      if (!detail) return;
      const wasHidden = detail.hidden;
      detail.hidden = !wasHidden;
      detail.setAttribute("data-opened", wasHidden ? "true" : "false");
    },
    // Bind the listener to the poller's lifecycle so dispose() removes it: no
    // leaked listener, and a re-init does not stack a duplicate listener that
    // would toggle the disclosure twice (net no-op → it never opens).
    signal ? { signal } : undefined,
  );
}

async function pollSignoffSnapshot({ url = "/api/signoff", fetchFn = fetch } = {}) {
  const response = await fetchFn(url);
  if (!response.ok) throw new Error(`signoff poll failed: ${response.status}`);
  return response.json();
}

function startPhaseTrackerPoller(root, opts = {}) {
  const { url = "/api/signoff", intervalMs = POLL_INTERVAL_MS, fetchFn = fetch } = opts;
  const controller = new AbortController();
  wireClickThrough(root, controller.signal);
  let inFlight = false;
  let disposed = false;
  const tick = async () => {
    // Skip while a previous poll is still in flight so a slow response cannot
    // land AFTER a newer one and flip a cell back to a stale state; and never
    // mutate the DOM once the poller has been disposed.
    if (inFlight || disposed) return;
    inFlight = true;
    try {
      const snapshot = await pollSignoffSnapshot({ url, fetchFn });
      if (!disposed) applySignoffSnapshot(root, snapshot);
    } catch {
      // Keep the last-known-good render on a transient poll failure (mirrors
      // masthead.js's tick catch — real disconnect handling is Story 5.20).
    } finally {
      inFlight = false;
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);
  return () => {
    disposed = true;
    window.clearInterval(handle);
    // Remove the click listener wired above (AbortController) so dispose fully
    // tears down — no leaked listener, no duplicate-listener stacking.
    controller.abort();
  };
}

export {
  POLL_INTERVAL_MS,
  applySignoffSnapshot,
  pollSignoffSnapshot,
  startPhaseTrackerPoller,
  wireClickThrough,
};
