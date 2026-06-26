/**
 * Activity Feed (Story 5.11 / UX §6.8).
 *
 * Last 50 agent runs with 5 fields; incremental prepend on poll (DD-06).
 */

const OUTCOME_GLYPH = {
  approved: "check",
  rejected: "slash-circle",
  error: "error",
};

const OUTCOME_LABEL = {
  approved: "Approved",
  rejected: "Rejected",
  error: "Error",
};

function buildSyntheticEntries(count = 50) {
  const outcomes = ["approved", "rejected", "error"];
  const entries = [];
  for (let i = 0; i < count; i += 1) {
    const idx = count - i;
    const outcome = outcomes[i % outcomes.length];
    entries.push({
      id: `run-${String(idx).padStart(3, "0")}`,
      timestamp: `2026-06-26T10:${String(59 - (i % 60)).padStart(2, "0")}:00`,
      agentName: i % 3 === 0 ? "dev-story" : i % 3 === 1 ? "code-review" : "create-story",
      targetId: `5-${10 + (i % 5)}`,
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
  const glyphId = OUTCOME_GLYPH[outcome] || OUTCOME_GLYPH.error;
  const label = OUTCOME_LABEL[outcome] || OUTCOME_LABEL.error;

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

function createFeedEntry(entry) {
  const row = document.createElement("div");
  row.className = "activity-feed__entry";
  row.dataset.entryId = entry.id;

  const timestamp = document.createElement("span");
  timestamp.className = "activity-feed__timestamp";
  timestamp.textContent = entry.timestamp;

  const agent = document.createElement("span");
  agent.className = "activity-feed__agent";
  agent.textContent = entry.agentName;

  const target = document.createElement("span");
  target.className = "activity-feed__target";
  target.textContent = entry.targetId;

  const duration = document.createElement("span");
  duration.className = "activity-feed__duration";
  duration.textContent = entry.duration;

  row.append(timestamp, agent, target, createOutcomeGlyph(entry.outcome), duration);
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
    if (!existingIds.has(entry.id)) {
      list.insertBefore(createFeedEntry(entry), list.firstChild);
      existingIds.add(entry.id);
    }
  }

  while (list.children.length > 50) {
    list.removeChild(list.lastChild);
  }

  host._fixtureRef = data;
}

export function prependActivityFeedEntry(host, entry, fixture = SYNTHETIC_ACTIVITY_FEED_FIXTURE) {
  const data = fixture || SYNTHETIC_ACTIVITY_FEED_FIXTURE;
  const entries = [entry, ...(data.entries || [])];
  data.entries = entries.slice(0, 50);
  renderActivityFeed(host, data);
  return data;
}

class ActivityFeed extends HTMLElement {
  connectedCallback() {
    if (!this.hasAttribute("role")) {
      this.setAttribute("role", "log");
    }
    if (!this.hasAttribute("aria-live")) {
      this.setAttribute("aria-live", "polite");
    }
    renderActivityFeed(this, this._fixtureRef || SYNTHETIC_ACTIVITY_FEED_FIXTURE);
  }
}

if (!customElements.get("activity-feed")) {
  customElements.define("activity-feed", ActivityFeed);
}

export { OUTCOME_GLYPH, OUTCOME_LABEL, buildSyntheticEntries, createFeedEntry };
