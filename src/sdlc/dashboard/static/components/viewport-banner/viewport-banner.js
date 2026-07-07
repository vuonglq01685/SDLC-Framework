/**
 * Viewport degradation banner (Story 5.21 / UX §8.2, DD-04 desktop-only,
 * DD-17 degraded-but-functional).
 *
 * Below 1280 px the dashboard does NOT collapse — it gains horizontal scroll and
 * shows a persistent, dismissible info banner. Below 768 px the copy upgrades to
 * a desktop-only message. There is NO responsive/breakpoint layout, no hamburger,
 * no card stacking (DD-04 single layout; AC2 explicit).
 *
 * D1: reuses the `.alert`/`.info` (`--blue`) CSS treatment from stop-banner.css,
 *     NOT `createStopBannerElement` — STOP banners are non-dismissible; this one
 *     carries a single `×` dismiss (the §8.2 sanctioned exception to §7.12).
 * D2: viewport detection via two `matchMedia` change-listeners (never a resize
 *     handler); the `matchMedia` factory is injectable for deterministic tests.
 *     A dismiss is remembered per severity LEVEL (<1280 vs <768): crossing into a
 *     different level re-surfaces that level's copy, so dismissing the milder
 *     <1280 notice never silences the escalated <768 "desktop-only" warning
 *     (review 2026-07-07 D2).
 * D3: the `×` is `aria-label="Dismiss"`, keyboard-reachable (native <button>),
 *     removed instantly (no transition, DD-14); dismissal is session-scoped via
 *     sessionStorage — it reappears in a NEW tab/session (sessionStorage persists
 *     across an in-tab reload, so the notice is not re-shown on every reload);
 *     the banner is `role="status"` (informational). A copy swap updates the text
 *     IN PLACE rather than rebuilding the node, so screen readers are not
 *     re-announced and keyboard focus on the `×` is preserved (review 2026-07-07 P3).
 */

// Exact copy — verbatim from AC1/AC2 + UX §8.2. Do NOT paraphrase.
// prettier-ignore
const COPY_BELOW_1280 = "Dashboard is optimized for screens ≥ 1280 px. Some elements may overflow below this width.";
// prettier-ignore
const COPY_BELOW_768 = "This dashboard is desktop-only. Mobile / tablet are unsupported. Open on a screen ≥ 1280 px.";

// `.98px` upper bounds so the ≥1280 / ≥768 boundaries are exact (a device at
// exactly 1280 px is supported and shows no banner).
const QUERY_BELOW_1280 = "(max-width: 1279.98px)";
const QUERY_BELOW_768 = "(max-width: 767.98px)";

const DISMISS_STORAGE_KEY = "sdlc.viewport-banner.dismissed";
const DISMISS_ARIA_LABEL = "Dismiss";
const DISMISS_GLYPH = "×";
// A dismiss is scoped to the severity level shown when it was dismissed, so an
// escalation to a more-severe level re-surfaces its own copy (D2).
const DISMISS_LEVEL_BELOW_1280 = "below-1280";
const DISMISS_LEVEL_BELOW_768 = "below-768";

/** The severity level for the current viewport width. */
function dismissLevelForWidth(mqlBelow768) {
  return mqlBelow768.matches ? DISMISS_LEVEL_BELOW_768 : DISMISS_LEVEL_BELOW_1280;
}

/** Guarded read of the session dismiss level (restricted contexts → show banner). */
function readDismissed(storage) {
  try {
    const value = storage.getItem(DISMISS_STORAGE_KEY);
    return value === DISMISS_LEVEL_BELOW_1280 || value === DISMISS_LEVEL_BELOW_768
      ? value
      : null;
  } catch {
    // sessionStorage may be unavailable (private mode / sandboxed): fail OPEN
    // (show the banner) rather than silently suppressing it.
    return null;
  }
}

/** Guarded write of the session dismiss level. */
function markDismissed(storage, level) {
  try {
    storage.setItem(DISMISS_STORAGE_KEY, level);
  } catch {
    // sessionStorage may be unavailable in restricted contexts — no-op.
  }
}

function copyForWidth(mqlBelow768) {
  return mqlBelow768.matches ? COPY_BELOW_768 : COPY_BELOW_1280;
}

function createBannerElement(text, { onDismiss }) {
  const banner = document.createElement("aside");
  banner.className = "viewport-banner alert info";
  banner.setAttribute("role", "status");

  const message = document.createElement("p");
  message.className = "viewport-banner__text";
  message.textContent = text;

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "viewport-banner__dismiss";
  dismiss.setAttribute("aria-label", DISMISS_ARIA_LABEL);
  dismiss.textContent = DISMISS_GLYPH;
  dismiss.addEventListener("click", onDismiss);

  banner.append(message, dismiss);
  return banner;
}

function resolveMediaQueryFn(opts) {
  if (opts.mediaQueryFn) {
    return opts.mediaQueryFn;
  }
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    return window.matchMedia.bind(window);
  }
  return null;
}

function resolveStorage(opts) {
  if (opts.storage) {
    return opts.storage;
  }
  return typeof sessionStorage !== "undefined" ? sessionStorage : null;
}

/**
 * Mount the viewport banner into `host` and keep it in sync with the viewport
 * via matchMedia. Returns a dispose function (also stashed on
 * `host._stopViewportBanner`) that removes the listeners and the banner.
 */
function startViewportBanner(host, opts = {}) {
  const mediaQueryFn = resolveMediaQueryFn(opts);
  const storage = resolveStorage(opts);
  if (!mediaQueryFn) {
    return () => {};
  }

  // Idempotent: dispose any prior instance on this host before re-wiring so a
  // second mount cannot leak the first instance's change listeners (P4).
  if (typeof host._stopViewportBanner === "function") {
    host._stopViewportBanner();
  }

  const mqlBelow1280 = mediaQueryFn(QUERY_BELOW_1280);
  const mqlBelow768 = mediaQueryFn(QUERY_BELOW_768);
  // The viewport level (if any) the user dismissed this session.
  let dismissedLevel = readDismissed(storage);

  const clear = () => {
    host.querySelectorAll(":scope > .viewport-banner").forEach((node) => node.remove());
  };

  const onDismiss = () => {
    dismissedLevel = dismissLevelForWidth(mqlBelow768);
    markDismissed(storage, dismissedLevel);
    clear();
  };

  const update = () => {
    // ≥ 1280 px (AC1 is "< 1280 px") → no banner.
    if (!mqlBelow1280.matches) {
      clear();
      return;
    }
    const level = dismissLevelForWidth(mqlBelow768);
    // Dismissed AT THIS level this session → stay hidden. Crossing into a
    // different (e.g. escalated <768) level re-shows that level's copy (D2).
    if (dismissedLevel === level) {
      clear();
      return;
    }
    const text = copyForWidth(mqlBelow768);
    const existing = host.querySelector(":scope > .viewport-banner");
    if (existing) {
      // In-place copy swap: keep the same role=status node so screen readers are
      // not re-announced and keyboard focus on the × is preserved (P3).
      const message = existing.querySelector(".viewport-banner__text");
      if (message) {
        message.textContent = text;
      }
      return;
    }
    host.insertBefore(createBannerElement(text, { onDismiss }), host.firstChild);
  };

  const onChange = () => update();
  mqlBelow1280.addEventListener("change", onChange);
  mqlBelow768.addEventListener("change", onChange);
  update();

  const dispose = () => {
    mqlBelow1280.removeEventListener("change", onChange);
    mqlBelow768.removeEventListener("change", onChange);
    clear();
    delete host._stopViewportBanner;
  };
  host._stopViewportBanner = dispose;
  return dispose;
}

export {
  COPY_BELOW_1280,
  COPY_BELOW_768,
  DISMISS_ARIA_LABEL,
  DISMISS_STORAGE_KEY,
  QUERY_BELOW_768,
  QUERY_BELOW_1280,
  markDismissed,
  readDismissed,
  startViewportBanner,
};
