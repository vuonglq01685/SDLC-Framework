/**
 * Backlog Tree real-hierarchy poller + URL-hash persistence (Story 5.15 D1-D3).
 *
 * NOT a rebuild of the FROZEN 5.10 backlog-tree substrate — the render /
 * keyboard / a11y internals in `backlog-tree.js` (renderEpic/renderStory/
 * renderTaskRow, collectVisibleExpanders/setRovingTabindex/focusExpanderById,
 * bindTreeKeyboard, the click handler) stay exactly as 5.10 froze them. This
 * is a small plain-script poller — mirrors `phase-tracker-live.js` /
 * `masthead.js` (`setInterval(tick, 3000)`) — that reads the Task-1
 * `/api/backlog` seam (pure server-side nesting adapter, never `/state.json`
 * — D1) and feeds the derived Epic->Story->Task nest into the frozen
 * `renderBacklogTree(host, fixture)` swap point.
 *
 * D3 (URL-hash expand/collapse persistence — new to 5.15; 5.10 kept expand
 * state in-memory only, `node.expanded`, with no URL/storage seam):
 *   - Grammar: `#backlog=<comma-separated canonical ids>`.
 *   - Read-on-load + `hashchange`: ids are validated against the Story 1.6
 *     canonical regex shape BEFORE use; unknown/malformed ids are silently
 *     ignored (forward-compat, no throw).
 *   - Write-on-toggle: rather than rewiring the frozen click/keydown
 *     handlers, a `MutationObserver` watches for `childList` changes on the
 *     host (every toggle/keyboard action re-renders via `host.replaceChildren()`
 *     — see backlog-tree.js `renderBacklogTree`) and re-derives the expanded
 *     canonical-id set straight from the rendered `aria-expanded` DOM state,
 *     then writes it to the hash via `history.replaceState` (no new history
 *     entry per toggle).
 *   - Expand state survives the 3 s poll re-render: each fetched snapshot
 *     starts fully collapsed (server has no expand state), so the last-known
 *     expanded-id set is re-applied to the freshly-fetched fixture before
 *     every render.
 */

import { renderBacklogTree } from "./backlog-tree.js";

const POLL_INTERVAL_MS = 3_000;
const HASH_KEY = "backlog";

// Mirrors src/sdlc/ids/parsers.py EPIC_ID_REGEX/STORY_ID_REGEX/TASK_ID_REGEX
// (Story 1.6) for hash-value injection-safety validation. Kept in sync by
// tests/unit/dashboard/test_backlog_tree_live_source.py.
const EPIC_ID_REGEX = /^EPIC-([a-z0-9]+(?:-[a-z0-9]+)*)$/;
const STORY_ID_REGEX = /^EPIC-([a-z0-9]+(?:-[a-z0-9]+)*)-S(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)$/;
const TASK_ID_REGEX =
  /^EPIC-([a-z0-9]+(?:-[a-z0-9]+)*)-S(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)-T(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)$/;

function isCanonicalId(id) {
  return (
    typeof id === "string" &&
    (EPIC_ID_REGEX.test(id) || STORY_ID_REGEX.test(id) || TASK_ID_REGEX.test(id))
  );
}

/** Read `#backlog=<ids>` from the current URL; unknown/malformed ids dropped. */
function readHashExpandedIds({ locationRef = window.location } = {}) {
  const raw = String(locationRef.hash || "").replace(/^#/, "");
  const match = new RegExp(`^${HASH_KEY}=(.*)$`).exec(raw);
  if (!match) {
    return new Set();
  }
  const ids = match[1].split(",").filter(isCanonicalId);
  return new Set(ids);
}

function collectExpandedIdsFromDom(host) {
  const ids = [];
  host.querySelectorAll('[role="treeitem"][aria-expanded="true"]').forEach((el) => {
    const nodeId = el.dataset.nodeId;
    if (isCanonicalId(nodeId)) {
      ids.push(nodeId);
    }
  });
  return ids;
}

/** Apply a known expanded-id set onto a freshly-fetched (fully-collapsed) fixture. */
function applyExpandedIds(fixture, expandedIds) {
  for (const epic of fixture.epics || []) {
    epic.expanded = expandedIds.has(epic.id);
    for (const story of epic.stories || []) {
      story.expanded = expandedIds.has(story.id);
    }
  }
  return fixture;
}

async function pollBacklogSnapshot({ url = "/api/backlog", fetchFn = fetch } = {}) {
  const response = await fetchFn(url);
  if (!response.ok) {
    throw new Error(`backlog poll failed: ${response.status}`);
  }
  return response.json();
}

function startBacklogTreeLivePoller(host, opts = {}) {
  const {
    url = "/api/backlog",
    intervalMs = POLL_INTERVAL_MS,
    fetchFn = fetch,
    locationRef = window.location,
    historyRef = window.history,
  } = opts;

  let knownExpandedIds = readHashExpandedIds({ locationRef });
  let lastHashValue = null;
  let disposed = false;
  let inFlight = false;

  function writeHashIfChanged(ids) {
    const sorted = [...ids].sort();
    const serialized = sorted.length > 0 ? `${HASH_KEY}=${sorted.join(",")}` : "";
    if (serialized === lastHashValue) {
      return;
    }
    lastHashValue = serialized;
    const nextUrl = new URL(locationRef.href);
    nextUrl.hash = serialized;
    historyRef.replaceState(null, "", nextUrl.toString());
  }

  // Every toggle/keyboard action re-renders via host.replaceChildren() (a
  // childList mutation) — never an in-place attribute flip — so a
  // childList observer (not an attribute observer) is what actually fires
  // for a user-driven expand/collapse (D3, no click/keydown rewiring).
  const observer = new MutationObserver(() => {
    knownExpandedIds = new Set(collectExpandedIdsFromDom(host));
    writeHashIfChanged(knownExpandedIds);
  });
  observer.observe(host, { childList: true });

  function onHashChange() {
    knownExpandedIds = readHashExpandedIds({ locationRef });
    if (host._fixtureRef) {
      applyExpandedIds(host._fixtureRef, knownExpandedIds);
      renderBacklogTree(host, host._fixtureRef);
    }
  }
  window.addEventListener("hashchange", onHashChange);

  const tick = async () => {
    if (inFlight || disposed) {
      return;
    }
    inFlight = true;
    try {
      const data = await pollBacklogSnapshot({ url, fetchFn });
      if (disposed) {
        return;
      }
      applyExpandedIds(data, knownExpandedIds);
      renderBacklogTree(host, data);
    } catch {
      // Keep the last-known-good render on a transient poll failure (mirrors
      // phase-tracker-live.js / masthead.js's tick catch).
    } finally {
      inFlight = false;
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);
  return () => {
    disposed = true;
    window.clearInterval(handle);
    observer.disconnect();
    window.removeEventListener("hashchange", onHashChange);
  };
}

export {
  EPIC_ID_REGEX,
  STORY_ID_REGEX,
  TASK_ID_REGEX,
  POLL_INTERVAL_MS,
  applyExpandedIds,
  collectExpandedIdsFromDom,
  isCanonicalId,
  pollBacklogSnapshot,
  readHashExpandedIds,
  startBacklogTreeLivePoller,
};
