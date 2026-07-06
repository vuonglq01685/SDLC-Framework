/**
 * KPI Strip real-data poller (Story 5.17 D1-D4).
 *
 * Fetches `/api/dora` (Story 5.13) and maps the 7d/30d envelope onto the
 * FROZEN `renderKpiStrip` seam from Story 5.7 — renderer internals stay
 * untouched; only the data source changes.
 */

import { renderKpiStrip } from "./kpi-strip.js";

const POLL_INTERVAL_MS = 3_000;

const HIGHER_IS_BETTER = new Set(["deployment_frequency"]);
const LOWER_IS_BETTER = new Set(["lead_time", "change_failure_rate", "mttr"]);

const METRIC_ORDER = [
  "deployment_frequency",
  "lead_time",
  "change_failure_rate",
  "mttr",
];

const METRIC_LABELS = {
  deployment_frequency: "DEPLOY FREQUENCY",
  lead_time: "LEAD TIME FOR CHANGES",
  change_failure_rate: "CHANGE FAIL RATE",
  mttr: "MTTR",
};

const PLACEHOLDER_CELL = {
  label: "PROJECT KPI",
  state: "no-data",
  noDataReason: "Project KPI not yet wired",
};

const LOADING_CELLS = Array.from({ length: 5 }, (_, index) => ({
  label: index < 4 ? "—" : "PROJECT KPI",
  state: "no-data",
  noDataReason: "Loading",
}));

function isValidRatio(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isValidNonNegative(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function formatNumber(value) {
  const rounded = Math.round(value * 10) / 10;
  return String(rounded);
}

function metricComparisonValue(metricName, metric) {
  if (!metric || metric.data_status !== "ok") {
    return null;
  }
  if (metricName === "deployment_frequency") {
    return isValidNonNegative(metric.per_day) ? metric.per_day : null;
  }
  if (metricName === "change_failure_rate") {
    return isValidRatio(metric.value) ? metric.value : null;
  }
  return isValidNonNegative(metric.value) ? metric.value : null;
}

function formatDisplayValue(metricName, value) {
  if (metricName === "deployment_frequency") {
    // 1-decimal so sub-1/day rates (common for real teams) don't collapse to
    // "0"; consistent with the delta line's own `formatNumber`.
    return formatNumber(value);
  }
  if (metricName === "change_failure_rate") {
    return String(Math.round(value * 100));
  }
  return formatNumber(value);
}

function displayUnit(metricName) {
  if (metricName === "deployment_frequency") {
    return "/day";
  }
  if (metricName === "change_failure_rate") {
    return "%";
  }
  return "hrs";
}

function rawDirection(current, baseline) {
  if (current == null || baseline == null) {
    return "neutral";
  }
  const epsilon = 1e-9;
  if (Math.abs(current - baseline) < epsilon) {
    return "neutral";
  }
  return current > baseline ? "up" : "down";
}

function sentimentDirection(metricName, numericDirection) {
  if (numericDirection === "neutral") {
    return "neutral";
  }
  if (HIGHER_IS_BETTER.has(metricName)) {
    return numericDirection;
  }
  if (LOWER_IS_BETTER.has(metricName)) {
    return numericDirection === "up" ? "down" : "up";
  }
  return "neutral";
}

function formatDeltaMagnitude(metricName, current, baseline) {
  // Emit the ABSOLUTE magnitude only. Sentiment (good/bad) is carried by
  // `delta.direction` -> the frozen renderer's arrow + colour + `+`-for-up
  // prefix. A raw-signed negative here would collide with that `+` prefix and
  // render a doubled `+-` sign on every lower-is-better improvement.
  const magnitude = Math.abs(current - baseline);
  if (magnitude < 1e-9) {
    return "0";
  }
  if (metricName === "deployment_frequency") {
    return `${formatNumber(magnitude)}/day`;
  }
  if (metricName === "change_failure_rate") {
    return `${formatNumber(magnitude * 100)}%`;
  }
  return `${formatNumber(magnitude)}h`;
}

function insufficientReason(metricName) {
  return `Insufficient data for ${METRIC_LABELS[metricName] || metricName}`;
}

function mapMetricCell(metricName, metric7d, metric30d) {
  const label = METRIC_LABELS[metricName] || metricName;
  if (!metric7d || metric7d.data_status === "insufficient_data") {
    return { label, state: "no-data", noDataReason: insufficientReason(metricName) };
  }

  const current = metricComparisonValue(metricName, metric7d);
  if (current == null) {
    return {
      label,
      state: "no-data",
      noDataReason: `Invalid data for ${label}`,
    };
  }

  const baseline = metricComparisonValue(metricName, metric30d);
  let delta;
  if (baseline == null) {
    delta = { direction: "neutral", text: "no 30d baseline" };
  } else {
    const numeric = rawDirection(current, baseline);
    delta = {
      direction: sentimentDirection(metricName, numeric),
      text: `${formatDeltaMagnitude(metricName, current, baseline)} vs 30d`,
    };
  }

  return {
    label,
    state: "default",
    value: formatDisplayValue(metricName, current),
    unit: displayUnit(metricName),
    delta,
  };
}

/** Map one `/api/dora` envelope onto the renderer's 5-cell contract. */
function mapDoraToCells(payload) {
  const windows = payload && payload.windows;
  if (!windows || typeof windows !== "object") {
    return Array.from({ length: 4 }, (_, index) => ({
      label: METRIC_LABELS[METRIC_ORDER[index]] || "—",
      state: "no-data",
      noDataReason: "DORA payload missing windows",
    })).concat([PLACEHOLDER_CELL]);
  }

  const window7d = windows["7d"] || {};
  const window30d = windows["30d"] || {};
  const cells = METRIC_ORDER.map((metricName) =>
    mapMetricCell(metricName, window7d[metricName], window30d[metricName]),
  );
  cells.push({ ...PLACEHOLDER_CELL });
  return cells.slice(0, 5);
}

function cellsSignature(cells) {
  return JSON.stringify(cells);
}

async function pollDoraSnapshot({ url = "/api/dora", fetchFn = fetch, signal } = {}) {
  const response = await fetchFn(url, signal ? { signal } : undefined);
  if (!response.ok) {
    throw new Error(`dora poll failed: ${response.status}`);
  }
  return response.json();
}

/**
 * Start polling `/api/dora` on a 3 s cycle, feeding mapped cells into the
 * untouched `renderKpiStrip` seam. Returns a dispose function stashed on
 * `host._stopPoller` for `kpi-strip.js`'s `disconnectedCallback`.
 */
function startKpiStripLivePoller(host, opts = {}) {
  const { url = "/api/dora", intervalMs = POLL_INTERVAL_MS, fetchFn = fetch } = opts;
  let disposed = false;
  let inFlight = false;
  let controller = null;
  let lastSignature = null;

  renderKpiStrip(host, LOADING_CELLS);

  const tick = async () => {
    if (inFlight || disposed) {
      return;
    }
    inFlight = true;
    controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    try {
      const payload = await pollDoraSnapshot({
        url,
        fetchFn,
        signal: controller ? controller.signal : undefined,
      });
      if (!disposed) {
        const cells = mapDoraToCells(payload);
        const signature = cellsSignature(cells);
        if (signature !== lastSignature) {
          lastSignature = signature;
          renderKpiStrip(host, cells);
        }
      }
    } catch {
      // Keep the last-known-good render on a transient poll failure OR an
      // aborted in-flight request — never surface as a visible error state.
    } finally {
      inFlight = false;
      controller = null;
    }
  };
  tick();
  const handle = window.setInterval(tick, intervalMs);

  const dispose = () => {
    disposed = true;
    window.clearInterval(handle);
    if (controller) {
      controller.abort();
    }
  };
  host._stopPoller = dispose;
  return dispose;
}

export {
  LOADING_CELLS,
  mapDoraToCells,
  pollDoraSnapshot,
  startKpiStripLivePoller,
};
