/**
 * Tabs component (Story 5.11 / UX §6.8).
 *
 * WAI-ARIA tablist/tab/tabpanel with manual-activation keyboard pattern.
 * Mirrors backlog-tree roving-tabindex (PAT-2 + leaf-focus lesson).
 */

export const SYNTHETIC_TABS_FIXTURE = {
  activeTabId: "backlog",
  tabs: [
    { id: "backlog", label: "Backlog", count: 12 },
    { id: "activity", label: "Activity", count: 50 },
    { id: "alerts", label: "Alerts", count: 0 },
  ],
};

function panelId(tabId) {
  return `tabpanel-${tabId}`;
}

function tabId(tabKey) {
  return `tab-${tabKey}`;
}

function collectTabs(root) {
  const tablist = root.querySelector('[role="tablist"]');
  if (!tablist) {
    return [];
  }
  return Array.from(tablist.querySelectorAll('[role="tab"]'));
}

function setRovingTabindex(tabs, active) {
  for (const tab of tabs) {
    tab.tabIndex = tab === active ? 0 : -1;
  }
}

function createCounterPill(count, isActive) {
  const pill = document.createElement("span");
  pill.className = "tabs__counter";
  if (isActive) {
    pill.classList.add("tabs__counter--active");
  }
  pill.textContent = String(count);
  return pill;
}

function createTab(tab, isSelected) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "tabs__tab";
  button.id = tabId(tab.id);
  button.setAttribute("role", "tab");
  button.setAttribute("aria-selected", isSelected ? "true" : "false");
  button.setAttribute("aria-controls", panelId(tab.id));
  if (isSelected) {
    button.classList.add("tabs__tab--active");
  }

  const label = document.createElement("span");
  label.className = "tabs__label";
  label.textContent = tab.label;

  button.append(label, createCounterPill(tab.count ?? 0, isSelected));
  return button;
}

function createPanel(tab, isSelected) {
  const panel = document.createElement("div");
  panel.className = "tabs__panel";
  panel.id = panelId(tab.id);
  panel.setAttribute("role", "tabpanel");
  panel.setAttribute("aria-labelledby", tabId(tab.id));
  if (!isSelected) {
    panel.hidden = true;
  }

  const body = document.createElement("p");
  body.className = "tabs__panel-body";
  body.textContent = tab.panelBody || `${tab.label} panel content`;
  panel.appendChild(body);
  return panel;
}

function activateTab(host, fixture, tabKey, focusTab = false) {
  const data = fixture || SYNTHETIC_TABS_FIXTURE;
  data.activeTabId = tabKey;
  renderTabs(host, data, { preserveFocusId: focusTab ? tabKey : data.activeTabId });
  if (focusTab) {
    const tabs = collectTabs(host);
    const active = tabs.find((t) => t.id === tabId(tabKey)) || tabs[0];
    if (active) {
      setRovingTabindex(tabs, active);
      active.focus();
    }
  }
}

function bindTabsKeyboard(host) {
  host.addEventListener("keydown", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement) || target.getAttribute("role") !== "tab") {
      return;
    }

    const fixture = host._fixtureRef || SYNTHETIC_TABS_FIXTURE;
    const tabs = collectTabs(host);
    const index = tabs.indexOf(target);
    if (index < 0) {
      return;
    }

    let nextFocus = null;
    let activate = false;

    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        if (index > 0) {
          nextFocus = tabs[index - 1];
        }
        break;
      case "ArrowRight":
        event.preventDefault();
        if (index < tabs.length - 1) {
          nextFocus = tabs[index + 1];
        }
        break;
      case "Home":
        event.preventDefault();
        nextFocus = tabs[0];
        break;
      case "End":
        event.preventDefault();
        nextFocus = tabs[tabs.length - 1];
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        activate = true;
        break;
      default:
        break;
    }

    if (activate) {
      const tabKey = target.id.replace(/^tab-/, "");
      activateTab(host, fixture, tabKey, true);
      return;
    }

    if (nextFocus) {
      setRovingTabindex(tabs, nextFocus);
      nextFocus.focus();
    }
  });

  host.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const tab = target.closest('[role="tab"]');
    if (!tab || !host.contains(tab)) {
      return;
    }
    const tabKey = tab.id.replace(/^tab-/, "");
    const fixture = host._fixtureRef || SYNTHETIC_TABS_FIXTURE;
    activateTab(host, fixture, tabKey, true);
  });
}

export function renderTabs(host, fixture = SYNTHETIC_TABS_FIXTURE, options = {}) {
  const data = fixture || SYNTHETIC_TABS_FIXTURE;
  const activeId = options.preserveFocusId || data.activeTabId || data.tabs?.[0]?.id;
  host.replaceChildren();

  const tablist = document.createElement("div");
  tablist.className = "tabs";
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", "Dashboard sections");

  const panelsWrap = document.createElement("div");
  panelsWrap.className = "tabs__panels";

  for (const tab of data.tabs || []) {
    const isSelected = tab.id === activeId;
    tablist.appendChild(createTab(tab, isSelected));
    panelsWrap.appendChild(createPanel(tab, isSelected));
  }

  host.append(tablist, panelsWrap);

  const tabs = collectTabs(host);
  let active = tabs.find((t) => t.id === tabId(activeId)) || tabs[0];
  if (active) {
    setRovingTabindex(tabs, active);
  }

  host._fixtureRef = data;
  if (!host._keyboardBound) {
    bindTabsKeyboard(host);
    host._keyboardBound = true;
  }
}

class DashboardTabs extends HTMLElement {
  connectedCallback() {
    renderTabs(this, this._fixtureRef || SYNTHETIC_TABS_FIXTURE);
  }
}

if (!customElements.get("dashboard-tabs")) {
  customElements.define("dashboard-tabs", DashboardTabs);
}

export { collectTabs, setRovingTabindex };
