/**
 * <phase-tracker> container (Story 5.9 / UX §6.5).
 *
 * Five-column strip: [P1][S1][P2][S2][P3]. Read-only in v1.
 *
 * Thin ARIA-decorator: the grid + detail markup is author/server-supplied
 * (the committed fixture today; the real-data render is Story 5.14). This
 * element only stamps the landmark role/label — it does NOT synthesize a
 * default strip. (Review DEC-2/PAT-4: the former DEFAULT_STRIP/DEFAULT_ROWS/
 * `variant` default-render path was dead + untested because every consumer
 * pre-bakes its own children, so the early-return always fired.)
 */

function renderPhaseTracker(root) {
  root.setAttribute("role", "region");
  if (!root.getAttribute("aria-label")) {
    root.setAttribute("aria-label", "Phase tracker");
  }
}

class PhaseTracker extends HTMLElement {
  connectedCallback() {
    renderPhaseTracker(this);
  }
}

if (!customElements.get("phase-tracker")) {
  customElements.define("phase-tracker", PhaseTracker);
}

export { renderPhaseTracker };
