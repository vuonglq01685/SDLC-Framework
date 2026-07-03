/**
 * Activity Feed (Story 5.11 / UX §6.8; real-data swap Story 5.16 D1-D4).
 *
 * Last 50 agent runs with 6 fields (ts, agent, target, stage, outcome,
 * duration); incremental prepend on poll (DD-06). `renderActivityFeed` /
 * `prependActivityFeedEntry` stay the frozen render SEAM (5.11 review HIGH:
 * newest-on-top + evict-oldest) — 5.16 extends the entry shape (6th `stage`
 * cell) and folds four deferred hardening fixes (DEF-1..DEF-4, see below)
 * rather than rewriting the render loop.
 *
 * Real-data path (Task 3): `startActivityFeedLivePoller` fetches the
 * server-projected `/api/activity` envelope (already field-mapped + last-50
 * reverse-chron — see `dashboard/routes/activity.py` D1) and re-maps its
 * display keys (`ts`->`timestamp`, `durationMs`->a human `duration` string)
 * onto the SAME shape the synthetic fixture produces, then feeds it through
 * the untouched `renderActivityFeed` seam. It is NOT auto-started from
 * `connectedCallback` (a bare `<activity-feed>` still renders the synthetic
 * fixture, preserving the component-fixture + editorial-rhythm demo pages);
 * a page that wants real data calls `startActivityFeedLivePoller(host)`
 * explicitly — this becomes the default/only path once a real dashboard page
 * wires the element up (page assembly is out of this story's scope).
 */

const POLL_INTERVAL_MS = 3_000;

// D3 (folds DEF-3): real writer emits only {success, failed}; `approved`/
// `rejected`/`error` are back-compat aliases for the 5.11 synthetic
// vocabulary. Any OTHER outcome (future schema, corruption) must NOT be
// mislabeled as the red `error` glyph -- it gets a neutral treatment instead.
const OUTCOME_GLYPH = {
  success: "check",
  approved: "check",
  failed: "slash-circle",
  rejected: "slash-circle",
  error: "error",
};

const OUTCOME_LABEL = {
  success: "Success",
  approved: "Approved",
  failed: "Failed",
  rejected: "Rejected",
  error: "Error",
};

const NEUTRAL_OUTCOME_GLYPH = "warning";

function buildSyntheticEntries(count = 50) {
  const outcomes = ["approved", "rejected", "error"];
  const stages = ["requirements", "architecture", "implementation", "verification"];
  const entries = [];
  for (let i = 0; i < count; i += 1) {
    const idx = count - i;
    const outcome = outcomes[i % outcomes.length];
    entries.push({
      id: `run-${String(idx).padStart(3, "0")}`,
      timestamp: `2026-06-26T10:${String(59 - (i % 60)).padStart(2, "0")}:00`,
      agentName: i % 3 === 0 ? "dev-story" : i % 3 === 1 ? "code-review" : "create-story",
      targetId: `5-${10 + (i % 5)}`,
      stage: stages[i % stages.length],
      outcome,
      duration: `${1 + (i % 9)}m ${10 + (i % 50)}s`,
    });
  }
  return entries;
}

export const SYNTHETIC_ACTIVITY_FEED_FIXTURE = {
  entries: buildSyntheticEntries(50),
};

function createOutcomeGlyph(outcome) {
  const known = Object.prototype.hasOwnProperty.call(OUTCOME_GLYPH, outcome);
  const glyphId = known ? OUTCOME_GLYPH[outcome] : NEUTRAL_OUTCOME_GLYPH;
  // DEF-3: an unknown outcome renders its own raw text (never silently
  // relabeled), so an operator can see exactly what the untrusted file said.
  const label = known ? OUTCOME_LABEL[outcome] : String(outcome ?? "—");

  const wrap = document.createElement("span");
  wrap.className = "activity-feed__outcome";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "activity-feed__outcome-icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "14");
  svg.setAttribute("height", "14");

  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `/static/icons/sprite.svg#${glyphId}`);
  svg.appendChild(use);

  const text = document.createElement("span");
  text.className = "activity-feed__outcome-label";
  text.textContent = label;

  wrap.append(svg, text);
  return wrap;
}

function createFeedEntry(entry, entryKey) {
  const row = document.createElement("div");
  row.className = "activity-feed__entry";
  // DEF-2: key consistently on both the dataset write (here) and the
  // existingIds dedupe check (renderActivityFeed) — a real row always
  // carries `id` (mapped from `run_id`), this is a defensive fallback only.
  row.dataset.entryId = entryKey;

  // DEF-4: a missing field must never render the literal string "undefined".
  const timestamp = document.createElement("span");
  timestamp.className = "activity-feed__timestamp";
  timestamp.textContent = entry.timestamp ?? "—";

  const agent = document.createElement("span");
  agent.className = "activity-feed__agent";
  agent.textContent = entry.agentName ?? "—";

  const target = document.createElement("span");
  target.className = "activity-feed__target";
  target.textContent = entry.targetId ?? "—";

  const stage = document.createElement("span");
  stage.className = "activity-feed__stage";
  stage.textContent = entry.stage ?? "—";

  const duration = document.createElement("span");
  duration.className = "activity-feed__duration";
  duration.textContent = entry.duration ?? "—";

  // Field order mirrors AC1: ts, agent name, target id, stage, outcome, duration_ms.
  row.append(timestamp, agent, target, stage, createOutcomeGlyph(entry.outcome), duration);
  return row;
}

function trimToLast50(list) {
  const entries = list.entries || [];
  if (entries.length <= 50) {
    return entries;
  }
  return entries.slice(0, 50);
}

export function renderActivityFeed(host, fixture = SYNTHETIC_ACTIVITY_FEED_FIXTURE) {
  const data = fixture || SYNTHETIC_ACTIVITY_FEED_FIXTURE;
  const entries = trimToLast50(data);

  let list = host.querySelector(".activity-feed__list");
  if (!list) {
    list = document.createElement("div");
    list.className = "activity-feed__list";
    list.setAttribute("tabindex", "0");
    if (!host.firstChild) {
      host.appendChild(list);
    } else {
      host.insertBefore(list, host.firstChild);
    }
  }

  const existingIds = new Set(
    Array.from(list.querySelectorAll(".activity-feed__entry")).map((el) => el.dataset.entryId),
  );

  // entries are newest-first; insert oldest -> newest before firstChild so the newest
  // entry lands on top and list.lastChild is genuinely the oldest (AC2: "older entries
  // scroll out"). Existing nodes are skipped, so a single-entry poll only prepends the
  // new row (incremental render, DD-06).
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i];
    // DEF-2: a missing `id` must not collapse every such row onto the dedupe
    // key `"undefined"` (which would cap the feed at one undefined-id row);
    // fall back to a per-render positional key, applied consistently here
    // and in createFeedEntry.
    const entryKey = entry.id ?? `row-${i}`;
    if (!existingIds.has(entryKey)) {
      list.insertBefore(createFeedEntry(entry, entryKey), list.firstChild);
      existingIds.add(entryKey);
    }
  }

  while (list.children.length > 50) {
    list.removeChild(list.lastChild);
  }

  // DEF-1: store this host's OWN state object — never the shared singleton
  // reference mutated in place. `prependActivityFeedEntry` below always
  // builds a fresh `{ entries }` object per call, so two `<activity-feed>`
  // hosts sharing the same starting fixture never overwrite each other's
  // subsequently-appended entries.
  host._fixtureRef = data;
}

export function prependActivityFeedEntry(host, entry, fixture) {
  // DEF-1: read from (never write into) the shared singleton. `base` may
  // legitimately alias `SYNTHETIC_ACTIVITY_FEED_FIXTURE` when no per-host
  // state exists yet, but the object built below is always NEW — the
  // singleton's `.entries` array is never reassigned/mutated.
  const base = fixture || host._fixtureRef || SYNTHETIC_ACTIVITY_FEED_FIXTURE;
  const nextEntries = [entry, ...(base.entries || [])].slice(0, 50);
  const data = { entries: nextEntries };
  renderActivityFeed(host, data);
  return data;
}

function formatDurationMs(durationMs) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs < 0) {
    return undefined;
  }
  const totalSeconds = Math.round(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

/** Map one `/api/activity` display entry onto the renderer's field contract. */
function mapServerEntry(raw) {
  return {
    id: raw && raw.id,
    timestamp: raw && raw.ts,
    agentName: raw && raw.agentName,
    targetId: raw && raw.targetId,
    stage: raw && raw.stage,
    outcome: raw && raw.outcome,
    duration: formatDurationMs(raw && raw.durationMs),
  };
}

async function pollActivityFeedSnapshot({ url = "/api/activity", fetchFn = fetch } = {}) {
  const response = await fetchFn(url);
  if (!response.ok) {
    throw new Error(`activity feed poll failed: ${response.status}`);
  }
  const payload = await response.json();
  const rawEntries = (payload && payload.entries) || [];
  return { entries: rawEntries.map(mapServerEntry) };
}

/**
 * Start polling `/api/activity` on a 3 s cycle (Task 3), feeding mapped
 * entries into the untouched `renderActivityFeed` seam so new rows prepend
 * and existing DOM nodes are left alone (NFR-PERF-4). Returns a dispose
 * function that stops the timer (mirrors phase-tracker-live.js /
 * backlog-tree-live.js's poller shape).
 */
export function startActivityFeedLivePoller(host, opts = {}) {
  const { url = "/api/activity", intervalMs = POLL_INTERVAL_MS, fetchFn = fetch } = opts;
  let disposed = false;
  let inFlight = false;
  const tick = async () => {
    if (inFlight || disposed) return;
    inFlight = true;
    try {
      const data = await pollActivityFeedSnapshot({ url, fetchFn });
      if (!disposed) renderActivityFeed(host, data);
    } catch {
      // Keep the last-known-good render on a transient poll failure (mirrors
      // masthead.js / phase-tracker-live.js's tick catch).
    } finally {
      inFlight = false;
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);
  return () => {
    disposed = true;
    window.clearInterval(handle);
  };
}

class ActivityFeed extends HTMLElement {
  connectedCallback() {
    if (!this.hasAttribute("role")) {
      this.setAttribute("role", "log");
    }
    if (!this.hasAttribute("aria-live")) {
      this.setAttribute("aria-live", "polite");
    }
    // A host marked `data-source="live"` (set in markup BEFORE this element
    // upgrades, e.g. activity-feed-live.fixture.html) is driven exclusively
    // by `startActivityFeedLivePoller` — auto-rendering the synthetic fixture
    // here first would flash 50 fake rows before the real poll lands.
    if (this.dataset.source === "live") {
      return;
    }
    renderActivityFeed(this, this._fixtureRef || SYNTHETIC_ACTIVITY_FEED_FIXTURE);
  }
}

if (!customElements.get("activity-feed")) {
  customElements.define("activity-feed", ActivityFeed);
}

export { OUTCOME_GLYPH, OUTCOME_LABEL, buildSyntheticEntries, createFeedEntry };
