/**
 * <backlog-tree> custom element (Story 5.10 / UX §6.6).
 *
 * WAI-ARIA tree with roving tabindex on `.tree-expander` (DD-15 focus ring).
 */

import {
  PILL_KIND_VARIANTS,
  PILL_STATUS_VARIANTS,
  createFlowPillGroup,
  createPillElement,
} from "../pills/pills.js";

/** Synthetic Epic → Story → Task fixture (Story 5.10 — not state.json). */
export const SYNTHETIC_TREE_FIXTURE = {
  currentTaskId: "EPIC-stripe-S04-T01",
  epics: [
    {
      id: "EPIC-stripe-webhook",
      kind: "EPIC",
      name: "Stripe webhook pipeline",
      flow: ["research", "epics", "stories"],
      meta: "phase 3 · 4 stories",
      pct: "62%",
      expanded: true,
      stories: [
        {
          id: "EPIC-stripe-S04",
          kind: "STORY",
          name: "Idempotency handling",
          status: "in-progress",
          meta: "2 tasks",
          pct: "50%",
          expanded: true,
          tasks: [
            {
              id: "EPIC-stripe-S04-T01",
              kind: "TASK",
              name: "Redis key design",
              status: "done",
              meta: "T01",
            },
            {
              id: "EPIC-stripe-S04-T02",
              kind: "TASK",
              name: "Handler integration",
              status: "pending",
              meta: "T02",
            },
          ],
        },
        {
          id: "EPIC-stripe-S05",
          kind: "STORY",
          name: "Signature verification",
          status: "pending",
          meta: "3 tasks",
          pct: "0%",
          expanded: false,
          tasks: [
            {
              id: "EPIC-stripe-S05-T01",
              kind: "TASK",
              name: "Secret rotation",
              status: "pending",
              meta: "T01",
            },
          ],
        },
      ],
    },
  ],
};


function kindVariant(kind) {
  const key = String(kind || "TASK").toUpperCase();
  return PILL_KIND_VARIANTS[key] || PILL_KIND_VARIANTS.TASK;
}

function statusVariant(status) {
  const key = String(status || "pending").toLowerCase();
  return PILL_STATUS_VARIANTS[key] || PILL_STATUS_VARIANTS.pending;
}

function createChevronSvg(expanded) {
  const glyph = expanded ? "chevron-down" : "chevron-right";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `/static/icons/sprite.svg#${glyph}`);
  svg.appendChild(use);
  return svg;
}

function createInlineCode(text) {
  const code = document.createElement("code");
  code.className = "inline-code";
  code.textContent = text;
  return code;
}

function createExpander({ nodeId, expanded, isLeaf, label }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = isLeaf ? "tree-expander tree-expander--leaf" : "tree-expander";
  btn.dataset.nodeId = nodeId;
  btn.setAttribute("aria-label", label || (expanded ? "Collapse" : "Expand"));
  // aria-expanded lives on the role="treeitem" wrapper (single source of
  // truth) — not duplicated on this inner button (DEC-1 / PAT-6).
  btn.appendChild(createChevronSvg(expanded));
  return btn;
}

/** §7.3: kind badge immediately left of the record name. */
function appendKindBadgeLeftOfName(parent, kind, nameText) {
  parent.appendChild(createPillElement(kindVariant(kind)));
  const nameEl = document.createElement("span");
  nameEl.className = "name";
  nameEl.textContent = nameText;
  parent.appendChild(nameEl);
}

function renderTaskRow(task, { currentTaskId, posinset, setsize }) {
  const row = document.createElement("div");
  row.className = "tree-task";
  row.setAttribute("role", "treeitem");
  row.setAttribute("aria-level", "3");
  row.setAttribute("aria-setsize", String(setsize));
  row.setAttribute("aria-posinset", String(posinset));
  if (task.id === currentTaskId) {
    row.setAttribute("aria-current", "true");
  }

  row.appendChild(
    createExpander({
      nodeId: task.id,
      expanded: false,
      isLeaf: true,
      label: task.name,
    }),
  );

  row.appendChild(createPillElement(kindVariant(task.kind)));

  const nameWrap = document.createElement("span");
  nameWrap.className = "tree-task__name";
  nameWrap.textContent = task.name;
  row.appendChild(nameWrap);

  const meta = document.createElement("span");
  meta.className = "tree-task__meta";
  meta.appendChild(createInlineCode(task.id));
  meta.appendChild(document.createTextNode(` · ${task.meta}`));
  row.appendChild(meta);

  row.appendChild(createPillElement(statusVariant(task.status)));
  return row;
}


function renderStory(story, ctx) {
  const { currentTaskId, storyIndex, storyCount } = ctx;
  const expanded = story.expanded !== false;
  const isCurrentStory = (story.tasks || []).some((t) => t.id === currentTaskId);

  const wrap = document.createElement("div");
  wrap.className = "tree-story";
  wrap.setAttribute("role", "treeitem");
  wrap.setAttribute("aria-level", "2");
  wrap.setAttribute("aria-setsize", String(storyCount));
  wrap.setAttribute("aria-posinset", String(storyIndex + 1));
  wrap.setAttribute("aria-expanded", expanded ? "true" : "false");
  // aria-current marks exactly ONE node — the current task row (PAT-1).
  // The story ancestor only gets a visual highlight class, not aria-current.
  if (isCurrentStory) {
    wrap.classList.add("is-current-ancestor");
  }
  wrap.dataset.nodeId = story.id;

  const head = document.createElement("div");
  head.className = "tree-story-head";

  head.appendChild(
    createExpander({
      nodeId: story.id,
      expanded,
      isLeaf: false,
      label: `Story ${story.name}`,
    }),
  );

  appendKindBadgeLeftOfName(head, story.kind, story.name);
  head.appendChild(createPillElement(statusVariant(story.status)));

  const meta = document.createElement("span");
  meta.className = "meta-line";
  meta.appendChild(createInlineCode(story.id));
  meta.appendChild(document.createTextNode(` · ${story.meta}`));
  head.appendChild(meta);

  const pct = document.createElement("span");
  pct.className = "pct";
  pct.textContent = story.pct || "—";
  head.appendChild(pct);

  wrap.appendChild(head);

  const body = document.createElement("div");
  body.className = expanded ? "tree-story-body" : "tree-story-body is-collapsed";
  body.setAttribute("role", "group");
  const tasks = story.tasks || [];
  tasks.forEach((task, taskIndex) => {
    body.appendChild(
      renderTaskRow(task, {
        currentTaskId,
        posinset: taskIndex + 1,
        setsize: tasks.length,
      }),
    );
  });
  wrap.appendChild(body);
  return wrap;
}

function renderEpic(epic, ctx) {
  const { currentTaskId, epicIndex, epicCount } = ctx;
  const expanded = epic.expanded !== false;
  const stories = epic.stories || [];

  const wrap = document.createElement("div");
  wrap.className = "tree-epic";
  wrap.setAttribute("role", "treeitem");
  wrap.setAttribute("aria-level", "1");
  wrap.setAttribute("aria-setsize", String(epicCount));
  wrap.setAttribute("aria-posinset", String(epicIndex + 1));
  wrap.setAttribute("aria-expanded", expanded ? "true" : "false");
  wrap.dataset.nodeId = epic.id;

  const head = document.createElement("div");
  head.className = "tree-epic-head";

  head.appendChild(
    createExpander({
      nodeId: epic.id,
      expanded,
      isLeaf: false,
      label: `Epic ${epic.name}`,
    }),
  );

  appendKindBadgeLeftOfName(head, epic.kind, epic.name);
  if (epic.flow) {
    head.appendChild(createFlowPillGroup(epic.flow));
  }

  const meta = document.createElement("span");
  meta.className = "meta-line";
  meta.appendChild(createInlineCode(epic.id));
  meta.appendChild(document.createTextNode(` · ${epic.meta}`));
  head.appendChild(meta);

  const pct = document.createElement("span");
  pct.className = "pct";
  pct.textContent = epic.pct || "—";
  head.appendChild(pct);

  wrap.appendChild(head);

  const body = document.createElement("div");
  body.className = expanded ? "tree-epic-body" : "tree-epic-body is-collapsed";
  body.setAttribute("role", "group");
  stories.forEach((story, storyIndex) => {
    body.appendChild(
      renderStory(story, {
        currentTaskId,
        storyIndex,
        storyCount: stories.length,
      }),
    );
  });
  wrap.appendChild(body);
  return wrap;
}


function findNodeData(fixture, nodeId) {
  for (const epic of fixture.epics || []) {
    if (epic.id === nodeId) {
      return { node: epic, type: "epic" };
    }
    for (const story of epic.stories || []) {
      if (story.id === nodeId) {
        return { node: story, type: "story", parent: epic };
      }
      for (const task of story.tasks || []) {
        if (task.id === nodeId) {
          return { node: task, type: "task", parent: story, epic };
        }
      }
    }
  }
  return null;
}

function toggleExpanded(fixture, nodeId) {
  const hit = findNodeData(fixture, nodeId);
  if (!hit || hit.type === "task") {
    return;
  }
  hit.node.expanded = hit.node.expanded === false;
}

function parentNodeId(fixture, nodeId) {
  const hit = findNodeData(fixture, nodeId);
  if (!hit) {
    return null;
  }
  if (hit.type === "story") {
    return hit.parent.id;
  }
  if (hit.type === "task") {
    return hit.parent.id;
  }
  return null;
}

function collectVisibleExpanders(root) {
  const expanders = [];
  const tree = root.querySelector('[role="tree"]');
  if (!tree) {
    return expanders;
  }

  function visitTreeitem(item) {
    const epicHead = item.querySelector(":scope > .tree-epic-head");
    const storyHead = item.querySelector(":scope > .tree-story-head");
    let btn = null;
    if (epicHead) {
      btn = epicHead.querySelector(".tree-expander");
    } else if (storyHead) {
      btn = storyHead.querySelector(".tree-expander");
    } else if (item.classList.contains("tree-task")) {
      btn = item.querySelector(":scope > .tree-expander");
    }
    if (btn) {
      expanders.push(btn);
    }

    const body = item.querySelector(
      ":scope > .tree-epic-body, :scope > .tree-story-body",
    );
    if (body && !body.classList.contains("is-collapsed")) {
      for (const child of body.children) {
        if (child.getAttribute("role") === "treeitem") {
          visitTreeitem(child);
        }
      }
    }
  }

  for (const child of tree.children) {
    if (child.getAttribute("role") === "treeitem") {
      visitTreeitem(child);
    }
  }
  return expanders;
}

function setRovingTabindex(expanders, active) {
  for (const btn of expanders) {
    btn.tabIndex = btn === active ? 0 : -1;
  }
}

function focusExpanderById(host, fixture, nodeId) {
  renderBacklogTree(host, fixture, { preserveFocusId: nodeId });
  const expanders = collectVisibleExpanders(host);
  const focusBtn = expanders.find((b) => b.dataset.nodeId === nodeId) || expanders[0];
  if (focusBtn) {
    setRovingTabindex(expanders, focusBtn);
    focusBtn.focus();
  }
}

function bindTreeKeyboard(host) {
  host.addEventListener("keydown", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement) || !target.classList.contains("tree-expander")) {
      return;
    }
    // Resolve the LIVE fixture from the host (PAT-2) — never close over a
    // stale object, so re-renders with new data (5.15) stay consistent.
    const fixture = host._fixtureRef || SYNTHETIC_TREE_FIXTURE;
    const expanders = collectVisibleExpanders(host);
    const index = expanders.indexOf(target);
    if (index < 0) {
      return;
    }

    const nodeId = target.dataset.nodeId || "";
    const hit = findNodeData(fixture, nodeId);
    const isParent = hit && (hit.type === "epic" || hit.type === "story");
    const expanded = isParent && hit.node.expanded !== false;

    let nextFocus = null;
    let rerender = false;
    let pendingFocusId = null;

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (index < expanders.length - 1) {
          nextFocus = expanders[index + 1];
        }
        break;
      case "ArrowUp":
        event.preventDefault();
        if (index > 0) {
          nextFocus = expanders[index - 1];
        }
        break;
      case "ArrowRight":
        event.preventDefault();
        if (isParent && !expanded) {
          hit.node.expanded = true;
          rerender = true;
        }
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (isParent && expanded) {
          hit.node.expanded = false;
          rerender = true;
        } else {
          pendingFocusId = parentNodeId(fixture, nodeId);
          if (pendingFocusId) {
            rerender = true;
          }
        }
        break;
      case "Enter":
        event.preventDefault();
        if (isParent) {
          toggleExpanded(fixture, nodeId);
          rerender = true;
        }
        break;
      case "Home":
        event.preventDefault();
        nextFocus = expanders[0];
        break;
      case "End":
        event.preventDefault();
        nextFocus = expanders[expanders.length - 1];
        break;
      default:
        break;
    }

    if (rerender) {
      const focusId = pendingFocusId || nodeId;
      focusExpanderById(host, fixture, focusId);
      return;
    }

    if (nextFocus) {
      setRovingTabindex(expanders, nextFocus);
      nextFocus.focus();
    }
  });

  host.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const btn = target.closest(".tree-expander");
    if (!btn || btn.classList.contains("tree-expander--leaf")) {
      return;
    }
    const nodeId = btn.dataset.nodeId;
    if (!nodeId) {
      return;
    }
    const fixture = host._fixtureRef || SYNTHETIC_TREE_FIXTURE;
    toggleExpanded(fixture, nodeId);
    focusExpanderById(host, fixture, nodeId);
  });
}


export function renderBacklogTree(host, fixture = SYNTHETIC_TREE_FIXTURE, options = {}) {
  const data = fixture || SYNTHETIC_TREE_FIXTURE;
  const currentTaskId = data.currentTaskId || "";
  const epics = data.epics || [];

  host.replaceChildren();

  const tree = document.createElement("div");
  tree.className = "backlog-tree";
  tree.setAttribute("role", "tree");
  tree.setAttribute("aria-label", "Backlog");

  epics.forEach((epic, epicIndex) => {
    tree.appendChild(
      renderEpic(epic, {
        currentTaskId,
        epicIndex,
        epicCount: epics.length,
      }),
    );
  });

  host.appendChild(tree);

  const expanders = collectVisibleExpanders(host);
  const focusId = options.preserveFocusId;
  let active = expanders[0];
  if (focusId) {
    active = expanders.find((b) => b.dataset.nodeId === focusId) || active;
  }
  if (active) {
    setRovingTabindex(expanders, active);
  }

  // Set on EVERY render so the keyboard/click handlers always act on the
  // currently-rendered fixture, not the one captured at first bind (PAT-2).
  host._fixtureRef = data;
  if (!host._keyboardBound) {
    bindTreeKeyboard(host);
    host._keyboardBound = true;
  }
}

class BacklogTree extends HTMLElement {
  connectedCallback() {
    const fixture = this._fixtureRef || SYNTHETIC_TREE_FIXTURE;
    renderBacklogTree(this, fixture);
  }
}

if (!customElements.get("backlog-tree")) {
  customElements.define("backlog-tree", BacklogTree);
}

export {
  appendKindBadgeLeftOfName,
  collectVisibleExpanders,
  createExpander,
  renderEpic,
  renderStory,
  renderTaskRow,
};
