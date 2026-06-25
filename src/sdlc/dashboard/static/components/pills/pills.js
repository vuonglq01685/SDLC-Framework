/**
 * Pill family registry (Story 5.10 / UX §7.3, §7.9).
 *
 * D1: kind badges compose --type-mono-pill-size + font-weight:700 +
 *     --type-label-mono-sm-letter-spacing (0.14em).
 * D2: registry at static/components/pills/ per epic AC2.
 */

/** Kind badge variants (uppercase, solid bg, white text). */
export const PILL_KIND_VARIANTS = {
  EPIC: { className: "pill pill--kind-epic", label: "EPIC" },
  STORY: { className: "pill pill--kind-story", label: "STORY" },
  TASK: { className: "pill pill--kind-task", label: "TASK" },
};

/** Status pills (lowercase, soft bg). */
export const PILL_STATUS_VARIANTS = {
  done: { className: "pill pill--status-done", label: "done" },
  "in-progress": { className: "pill pill--status-in-progress", label: "in-progress" },
  pending: { className: "pill pill--status-pending", label: "pending" },
};

/** Stage pills (lowercase, pill radius, border + soft bg). */
export const PILL_STAGE_VARIANTS = {
  research: { className: "pill pill--stage", label: "research" },
  epics: { className: "pill pill--stage pill--stage-current", label: "epics" },
  stories: { className: "pill pill--stage", label: "stories" },
};

/** Flow pipeline steps (joined-edge fp group). */
export const PILL_FLOW_VARIANTS = {
  research: { className: "pill pill--flow", label: "research" },
  epics: { className: "pill pill--flow", label: "epics" },
  stories: { className: "pill pill--flow", label: "stories" },
};

/** Priority pills (lowercase, soft bg). */
export const PILL_PRIORITY_VARIANTS = {
  high: { className: "pill pill--priority-high", label: "high" },
  medium: { className: "pill pill--priority-medium", label: "medium" },
  low: { className: "pill pill--priority-low", label: "low" },
};

/** All registry groups for static-analysis contract tests. */
export const PILL_REGISTRY_GROUPS = {
  kind: PILL_KIND_VARIANTS,
  status: PILL_STATUS_VARIANTS,
  stage: PILL_STAGE_VARIANTS,
  flow: PILL_FLOW_VARIANTS,
  priority: PILL_PRIORITY_VARIANTS,
};

export function createPillElement(variant) {
  const span = document.createElement("span");
  span.className = variant.className;
  span.textContent = variant.label;
  return span;
}

export function createFlowPillGroup(steps) {
  const wrap = document.createElement("span");
  wrap.className = "fp";
  wrap.setAttribute("role", "presentation");
  for (const step of steps) {
    const key = String(step).toLowerCase();
    const variant = PILL_FLOW_VARIANTS[key];
    if (variant) {
      wrap.appendChild(createPillElement(variant));
    }
  }
  return wrap;
}
