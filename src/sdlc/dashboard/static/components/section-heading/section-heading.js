/**
 * Section-Block Heading (Story 5.11 / UX §7.8).
 *
 * Cross-cutting heading: serif title + right-aligned mono count.
 */

function renderSectionBlockHeading(host, { title, count, size = "display-3" } = {}) {
  host.replaceChildren();
  host.classList.add("section-block-heading");

  const heading = document.createElement("h2");
  heading.className = `section-block-heading__title section-block-heading__title--${size}`;
  heading.textContent = title || "";

  const countEl = document.createElement("span");
  countEl.className = "section-block-heading__count";
  // Nullish check (not `count || ""`): a numeric 0 is a legitimate count and
  // must render "0" — the prior falsy-coercion blanked it (DEF-6, 5.11 review).
  countEl.textContent = count == null ? "" : String(count);

  host.append(heading, countEl);
}

class SectionBlockHeading extends HTMLElement {
  static get observedAttributes() {
    return ["title", "count", "size"];
  }

  connectedCallback() {
    this._render();
  }

  attributeChangedCallback() {
    if (this.isConnected) {
      this._render();
    }
  }

  _render() {
    renderSectionBlockHeading(this, {
      title: this.getAttribute("title") || "",
      count: this.getAttribute("count") || "",
      size: this.getAttribute("size") || "display-3",
    });
  }
}

if (!customElements.get("section-block-heading")) {
  customElements.define("section-block-heading", SectionBlockHeading);
}

export { renderSectionBlockHeading };
