"""Playwright behavioral + a11y witness for the viewport banner (Story 5.21).

Drives matchMedia deterministically via an injected fake MediaQueryList
(``mediaQueryFn`` opt) and a Map-backed fake ``storage`` — never a real viewport
resize (web-testing determinism rule / D2). Covers AC1 (<1280 info banner +
dismiss + sessionStorage), AC2 (<768 upgraded copy, no layout collapse), AC3
(change crossings do not break), and the D3 a11y contract (labelled dismiss
button focusable, no transition, reduced-motion).
"""

from __future__ import annotations

import pytest

from dashboard._playwright_a11y import (
    AXE_BLOCK_TAGS,
    format_axe_violation,
    run_axe_scan,
    with_playwright_page,
)

pytestmark = [pytest.mark.integration]

_FIXTURE_PATH = "/static/components/viewport-banner/viewport-banner.fixture.html"
_MODULE = "/static/components/viewport-banner/viewport-banner.js"

# Exact copy, verbatim from AC1/AC2 + UX §8.2.
_COPY_BELOW_1280 = (
    "Dashboard is optimized for screens \u2265 1280 px. "
    "Some elements may overflow below this width."
)
_COPY_BELOW_768 = (
    "This dashboard is desktop-only. Mobile / tablet are unsupported. "
    "Open on a screen \u2265 1280 px."
)

# In-page helpers: a controllable fake MediaQueryList + factory + a Map-backed
# fake sessionStorage. Declared INSIDE the evaluated arrow function (page.evaluate
# takes a single expression), via `_script`.
_HARNESS = """
  function makeMql(matches) {
    const cbs = new Set();
    return {
      matches,
      media: "",
      addEventListener(type, cb) { if (type === "change") cbs.add(cb); },
      removeEventListener(type, cb) { cbs.delete(cb); },
      get listenerCount() { return cbs.size; },
      _emit(value) { this.matches = value; cbs.forEach((cb) => cb({ matches: value })); },
    };
  }
  function makeFactory(mql1280, mql768) {
    return (query) => (query.indexOf("767") !== -1 ? mql768 : mql1280);
  }
  function makeStorage() {
    const m = new Map();
    return {
      getItem: (k) => (m.has(k) ? m.get(k) : null),
      setItem: (k, v) => { m.set(k, String(v)); },
      removeItem: (k) => { m.delete(k); },
    };
  }
"""


def _script(body: str) -> str:
    return "async () => {\n" + _HARNESS + "\n" + body + "\n}"


def test_below_1280_mounts_info_banner_with_exact_copy(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(makeMql(true), makeMql(false)),
                storage: makeStorage(),
              }});
              const banner = host.querySelector('.viewport-banner');
              const dismiss = banner && banner.querySelector('button');
              const textEl = banner && banner.querySelector('.viewport-banner__text');
              return {{
                count: host.querySelectorAll('.viewport-banner').length,
                text: textEl ? textEl.textContent : null,
                role: banner ? banner.getAttribute('role') : null,
                isInfo: banner ? banner.classList.contains('info') : false,
                isAlert: banner ? banner.classList.contains('alert') : false,
                dismissLabel: dismiss ? dismiss.getAttribute('aria-label') : null,
                dismissTag: dismiss ? dismiss.tagName.toLowerCase() : null,
              }};
            """
            )
        )
        assert result["count"] == 1
        assert result["text"] == _COPY_BELOW_1280
        assert result["role"] == "status"
        assert result["isInfo"] is True
        assert result["isAlert"] is True
        assert result["dismissLabel"] == "Dismiss"
        assert result["dismissTag"] == "button"


def test_below_768_upgrades_copy_no_layout_collapse(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(makeMql(true), makeMql(true)),
                storage: makeStorage(),
              }});
              const textEl = host.querySelector('.viewport-banner__text');
              return {{
                text: textEl ? textEl.textContent : null,
                hamburgers: host.querySelectorAll('[class*="hamburger"], nav').length,
                collapsed: host.querySelectorAll('[style*="display: none"]').length,
              }};
            """
            )
        )
        assert result["text"] == _COPY_BELOW_768
        assert result["hamburgers"] == 0
        assert result["collapsed"] == 0


def test_at_or_above_1280_no_banner(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        count = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(makeMql(false), makeMql(false)),
                storage: makeStorage(),
              }});
              return host.querySelectorAll('.viewport-banner').length;
            """
            )
        )
        assert count == 0


def test_change_crossing_mounts_then_upgrades(
    running_dashboard: tuple[str, int, object],
) -> None:
    """AC3: a matchMedia change that crosses a boundary mounts / swaps, no break."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              const mql1280 = makeMql(false);
              const mql768 = makeMql(false);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(mql1280, mql768),
                storage: makeStorage(),
              }});
              const txt = () => {{
                const b = host.querySelector('.viewport-banner__text');
                return b ? b.textContent : null;
              }};
              const atWide = host.querySelectorAll('.viewport-banner').length;
              mql1280._emit(true);
              const below1280Text = txt();
              mql768._emit(true);
              const below768Text = txt();
              return {{ atWide, below1280Text, below768Text }};
            """
            )
        )
        assert result["atWide"] == 0
        assert result["below1280Text"] == _COPY_BELOW_1280
        assert result["below768Text"] == _COPY_BELOW_768


def test_dismiss_removes_banner_and_survives_session_reappears_next_load(
    running_dashboard: tuple[str, int, object],
) -> None:
    """AC1/D3: dismiss removes + sets sessionStorage flag; suppressed for the
    session (same storage), returns on a fresh session (new storage)."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const storage = makeStorage();
              const factory = () => makeFactory(makeMql(true), makeMql(false));

              const host1 = document.createElement('div');
              document.body.appendChild(host1);
              const stop1 = m.startViewportBanner(host1, {{ mediaQueryFn: factory(), storage }});
              const before = host1.querySelectorAll('.viewport-banner').length;
              host1.querySelector('.viewport-banner button').click();
              const afterClick = host1.querySelectorAll('.viewport-banner').length;
              stop1();

              const host2 = document.createElement('div');
              document.body.appendChild(host2);
              m.startViewportBanner(host2, {{ mediaQueryFn: factory(), storage }});
              const sameSession = host2.querySelectorAll('.viewport-banner').length;

              const host3 = document.createElement('div');
              document.body.appendChild(host3);
              m.startViewportBanner(host3, {{ mediaQueryFn: factory(), storage: makeStorage() }});
              const freshSession = host3.querySelectorAll('.viewport-banner').length;

              return {{ before, afterClick, sameSession, freshSession }};
            """
            )
        )
        assert result["before"] == 1
        assert result["afterClick"] == 0
        assert result["sameSession"] == 0
        assert result["freshSession"] == 1


def test_dismiss_below_1280_still_escalates_to_desktop_only_below_768(
    running_dashboard: tuple[str, int, object],
) -> None:
    """D2 (review 2026-07-07): dismissing the <1280 info banner must NOT silence
    the escalated <768 'desktop-only / unsupported' copy — the more-severe
    message re-surfaces when the viewport crosses below 768 px."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              const mql1280 = makeMql(true);
              const mql768 = makeMql(false);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(mql1280, mql768),
                storage: makeStorage(),
              }});
              // Dismiss the milder <1280 info banner.
              host.querySelector('.viewport-banner button').click();
              const afterDismiss = host.querySelectorAll('.viewport-banner').length;
              // Now cross below 768 -> the escalated copy must re-appear.
              mql768._emit(true);
              const textEl = host.querySelector('.viewport-banner__text');
              return {{
                afterDismiss,
                escalatedCount: host.querySelectorAll('.viewport-banner').length,
                escalatedText: textEl ? textEl.textContent : null,
              }};
            """
            )
        )
        assert result["afterDismiss"] == 0
        assert result["escalatedCount"] == 1
        assert result["escalatedText"] == _COPY_BELOW_768


def test_copy_swap_preserves_dismiss_focus_in_place(
    running_dashboard: tuple[str, int, object],
) -> None:
    """P3 (review 2026-07-07): a boundary crossing swaps the copy IN PLACE, so the
    same role=status node is reused and keyboard focus on the dismiss control
    survives (no teardown/rebuild that would drop focus to body or re-announce)."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              const mql1280 = makeMql(true);
              const mql768 = makeMql(false);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(mql1280, mql768),
                storage: makeStorage(),
              }});
              const dismiss = host.querySelector('.viewport-banner button');
              const banner = host.querySelector('.viewport-banner');
              dismiss.focus();
              const focusedBefore = document.activeElement === dismiss;
              // Cross below 768 -> copy swaps in place; the SAME nodes are kept.
              mql768._emit(true);
              return {{
                focusedBefore,
                sameButton: host.querySelector('.viewport-banner button') === dismiss,
                sameBanner: host.querySelector('.viewport-banner') === banner,
                focusedAfter: document.activeElement === dismiss,
                text: host.querySelector('.viewport-banner__text').textContent,
              }};
            """
            )
        )
        assert result["focusedBefore"] is True
        assert result["sameButton"] is True
        assert result["sameBanner"] is True
        assert result["focusedAfter"] is True
        assert result["text"] == _COPY_BELOW_768


def test_repeat_start_on_same_host_has_no_listener_leak(
    running_dashboard: tuple[str, int, object],
) -> None:
    """P4 (review 2026-07-07): a second startViewportBanner on the same host
    disposes the first instance, so matchMedia change listeners do not
    accumulate and exactly one banner remains."""
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              const mql1280 = makeMql(true);
              const mql768 = makeMql(false);
              const factory = makeFactory(mql1280, mql768);
              m.startViewportBanner(host, {{ mediaQueryFn: factory, storage: makeStorage() }});
              m.startViewportBanner(host, {{ mediaQueryFn: factory, storage: makeStorage() }});
              return {{
                banners: host.querySelectorAll('.viewport-banner').length,
                listeners1280: mql1280.listenerCount,
                listeners768: mql768.listenerCount,
              }};
            """
            )
        )
        assert result["banners"] == 1
        assert result["listeners1280"] == 1
        assert result["listeners768"] == 1


def test_dismiss_button_focusable_and_no_transition_reduced_motion(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        result = page.evaluate(
            _script(
                f"""
              const m = await import('{_MODULE}');
              const host = document.createElement('div');
              document.body.appendChild(host);
              m.startViewportBanner(host, {{
                mediaQueryFn: makeFactory(makeMql(true), makeMql(false)),
                storage: makeStorage(),
              }});
              const dismiss = host.querySelector('.viewport-banner button');
              dismiss.focus();
              const banner = host.querySelector('.viewport-banner');
              const cs = getComputedStyle(banner);
              const dcs = getComputedStyle(dismiss);
              return {{
                focused: document.activeElement === dismiss,
                tabindex: dismiss.getAttribute('tabindex'),
                bannerTransition: cs.transitionDuration,
                dismissTransition: dcs.transitionDuration,
                bannerAnimation: cs.animationName,
              }};
            """
            )
        )
        assert result["focused"] is True
        assert result["tabindex"] is None or int(result["tabindex"]) >= 0
        assert result["bannerTransition"] in ("0s", "")
        assert result["dismissTransition"] in ("0s", "")
        assert result["bannerAnimation"] == "none"


def test_axe_clean_when_banner_visible(
    running_dashboard: tuple[str, int, object],
) -> None:
    base_url, _port, _server = running_dashboard
    with with_playwright_page(f"{base_url}{_FIXTURE_PATH}") as page:
        page.wait_for_selector(".viewport-banner")
        blocking, _reported = run_axe_scan(page)
        assert not blocking, "; ".join(format_axe_violation(v) for v in blocking) + (
            f" (Level A tags: {sorted(AXE_BLOCK_TAGS)})"
        )
