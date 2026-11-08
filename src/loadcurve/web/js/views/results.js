// Step 4: what the analysis says about consumption: a stats table, three charts
// (hourly profile, load duration curve, monthly energy) and a load × hour heatmap.
//
// Charts are drawn with Chart.js (loaded as window.Chart from /vendor). They are
// rebuilt only when the result, the theme or the language changes, and without
// animation: on this page all ambient motion belongs to the hero.

import { formatEnergy, formatHour, formatNumber, formatPercent, formatPower, monthNames } from "../format.js";
import { language, t } from "../i18n.js";
import { activeTheme } from "../theme.js";

const W_PER_KW = 1000;

function cssColors() {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(name).trim();
  return {
    ink: read("--ink"),
    muted: read("--muted"),
    line: read("--line"),
    primary: read("--primary"),
    sun: read("--sun"),
    sunInk: read("--sun-ink"),
    duskFill: read("--dusk-fill"),
    font: read("--font-text"),
  };
}

/** "#1e7a3a" + alpha 0.2 -> "#1e7a3a33" (Chart.js needs a concrete colour). */
function withAlpha(hex, alpha) {
  return `${hex}${Math.round(alpha * 255).toString(16).padStart(2, "0")}`;
}

function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

// ---------- Stats ----------

function statsTable(analysis, lang) {
  const { start, end } = windowOf(analysis);
  const rows = [
    [t("results.whole_day"), analysis.whole_day],
    [t("results.daytime", { start, end }), analysis.daytime],
    [t("results.nighttime"), analysis.nighttime],
  ];
  const head = element("tr", {}, [
    element("th", { scope: "col" }, [t("results.period")]),
    ...["energy", "peak", "base", "load_factor"].map((key) =>
      element("th", { scope: "col" }, [t(`results.col_${key}`)]),
    ),
  ]);
  const body = rows.map(([label, stats]) =>
    element("tr", {}, [
      element("th", { scope: "row" }, [label]),
      element("td", {}, [formatEnergy(stats.energy_kwh, lang)]),
      element("td", {}, [t("results.at_hour", { value: formatPower(stats.peak_power_w, lang), hour: formatHour(stats.peak_hour) })]),
      element("td", {}, [t("results.at_hour", { value: formatPower(stats.base_power_w, lang), hour: formatHour(stats.base_hour) })]),
      element("td", {}, [formatPercent(stats.load_factor, lang)]),
    ]),
  );
  return [element("thead", {}, [head]), element("tbody", {}, body)];
}

function windowOf(analysis) {
  const hours = analysis.daytime_hours;
  return { start: formatHour(hours[0]), end: formatHour((hours.at(-1) + 1) % 24) };
}

// ---------- Charts ----------

function baseOptions(colors, { legend = false, yTitle }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: legend, labels: { color: colors.ink, boxWidth: 14 } },
      tooltip: { intersect: false, mode: "index" },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: colors.muted, maxRotation: 0 } },
      y: {
        beginAtZero: true,
        grid: { color: withAlpha(colors.line, 0.6) },
        ticks: { color: colors.muted },
        title: { display: true, text: yTitle, color: colors.muted },
      },
    },
  };
}

function hourlyChart(canvas, analysis, colors, lang) {
  const daytime = new Set(analysis.daytime_hours);
  const isDay = (hour) => daytime.has(hour);
  const options = baseOptions(colors, { yTitle: "kW" });
  options.plugins.tooltip.callbacks = {
    title: ([item]) => formatHour(item.dataIndex),
    label: (item) => formatPower(analysis.hourly_profile_w[item.dataIndex], lang),
  };
  return new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: analysis.hourly_profile_w.map((_, hour) => String(hour)),
      datasets: [
        {
          data: analysis.hourly_profile_w.map((watts) => watts / W_PER_KW),
          backgroundColor: analysis.hourly_profile_w.map((_, h) => (isDay(h) ? colors.sun : colors.duskFill)),
          borderColor: analysis.hourly_profile_w.map((_, h) => (isDay(h) ? colors.sunInk : colors.duskFill)),
          borderWidth: 1,
          borderRadius: 3,
        },
      ],
    },
    options,
  });
}

function durationChart(canvas, analysis, colors, lang) {
  const curve = analysis.load_duration_curve_w.map((watts) => watts / W_PER_KW);
  const mean = analysis.whole_day.mean_power_w / W_PER_KW;
  const options = baseOptions(colors, { legend: true, yTitle: "kW" });
  options.scales.x.title = { display: true, text: t("results.hours_at_or_above"), color: colors.muted };
  options.plugins.tooltip.callbacks = {
    title: ([item]) => t("results.hours_count", { count: item.dataIndex + 1 }),
    label: (item) => `${item.dataset.label}: ${formatPower(item.raw * W_PER_KW, lang)}`,
  };
  return new window.Chart(canvas, {
    type: "line",
    data: {
      labels: curve.map((_, index) => String(index + 1)),
      datasets: [
        {
          label: t("results.power"),
          data: curve,
          borderColor: colors.primary,
          backgroundColor: withAlpha(colors.primary, 0.18),
          fill: "origin",
          stepped: "before",
          pointRadius: 0,
        },
        {
          label: t("results.mean_power"),
          data: curve.map(() => mean),
          borderColor: colors.muted,
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    },
    options,
  });
}

function monthlyChart(canvas, analysis, colors, lang) {
  const months = analysis.monthly;
  const average = months.reduce((sum, month) => sum + month.energy_kwh, 0) / months.length;
  const options = baseOptions(colors, { legend: true, yTitle: "kWh" });
  options.scales.x.stacked = true;
  options.scales.y.stacked = true;
  options.plugins.tooltip.callbacks = {
    label: (item) => `${item.dataset.label}: ${formatEnergy(item.raw, lang)}`,
  };
  return new window.Chart(canvas, {
    data: {
      labels: monthNames(lang),
      datasets: [
        {
          type: "bar",
          label: t("results.by_day"),
          data: months.map((month) => month.daytime_energy_kwh),
          backgroundColor: colors.sun,
          borderColor: colors.sunInk,
          borderWidth: 1,
          stack: "energy",
        },
        {
          type: "bar",
          label: t("results.at_night"),
          data: months.map((month) => month.nighttime_energy_kwh),
          backgroundColor: colors.duskFill,
          stack: "energy",
        },
        {
          type: "line",
          label: t("results.monthly_average"),
          data: months.map(() => average),
          borderColor: colors.muted,
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          stack: "average",
        },
      ],
    },
    options,
  });
}

// ---------- Heatmap ----------

/** A table whose cells are shaded by the power each Load draws in each hour. */
function heatmap(analysis, lang) {
  const daytime = new Set(analysis.daytime_hours);
  const highest = Math.max(...analysis.loads.flatMap((load) => load.hourly_power_w), 1);
  const head = element("tr", {}, [
    element("th", { scope: "col" }, [t("loads.col_name")]),
    ...Array.from({ length: 24 }, (_, hour) =>
      element("th", { scope: "col", class: daytime.has(hour) ? "is-day" : "is-night" }, [String(hour)]),
    ),
  ]);
  const rows = analysis.loads.map((load) =>
    element("tr", {}, [
      element("th", { scope: "row" }, [load.name]),
      ...load.hourly_power_w.map((watts, hour) => {
        const share = Math.round((watts / highest) * 100);
        const label = t("results.heat_cell", { name: load.name, hour: formatHour(hour), power: formatPower(watts, lang) });
        return element("td", { title: label, style: `--heat: ${share}%` }, [
          element("span", { class: "visually-hidden" }, [formatPower(watts, lang)]),
        ]);
      }),
    ]),
  );
  return [element("thead", {}, [head]), element("tbody", {}, rows)];
}

// ---------- View ----------

export function createResults(root) {
  const empty = root.querySelector("[data-results-empty]");
  const panel = root.querySelector("[data-results]");
  const year = root.querySelector("[data-results-year]");
  const stats = root.querySelector("[data-results-stats]");
  const heat = root.querySelector("[data-heatmap]");
  const canvases = {
    hourly: root.querySelector('[data-chart="hourly"]'),
    duration: root.querySelector('[data-chart="duration"]'),
    monthly: root.querySelector('[data-chart="monthly"]'),
  };
  const charts = {};
  let drawnKey = null;
  let drawnResult = null;

  function draw(analysis, lang) {
    if (!window.Chart) return; // the vendor script failed to load; tables still show
    const colors = cssColors();
    window.Chart.defaults.font.family = colors.font;
    for (const chart of Object.values(charts)) chart.destroy();
    charts.hourly = hourlyChart(canvases.hourly, analysis, colors, lang);
    charts.duration = durationChart(canvases.duration, analysis, colors, lang);
    charts.monthly = monthlyChart(canvases.monthly, analysis, colors, lang);
  }

  function render(state) {
    const analysis = state.result?.analysis ?? null;
    empty.hidden = Boolean(analysis);
    panel.hidden = !analysis;
    if (!analysis) return;

    const lang = language();
    const key = `${activeTheme()}|${lang}`;
    if (state.result === drawnResult && key === drawnKey) return;
    drawnResult = state.result;
    drawnKey = key;

    year.textContent = t("results.year", {
      total: formatEnergy(analysis.annual_energy_kwh, lang),
      day: formatEnergy(analysis.annual_daytime_energy_kwh, lang),
      night: formatEnergy(analysis.annual_nighttime_energy_kwh, lang),
    });
    stats.replaceChildren(...statsTable(analysis, lang));
    heat.replaceChildren(...heatmap(analysis, lang));
    canvases.hourly.setAttribute(
      "aria-label",
      t("results.hourly_aria", {
        peak: formatPower(analysis.whole_day.peak_power_w, lang),
        hour: formatHour(analysis.whole_day.peak_hour),
      }),
    );
    canvases.duration.setAttribute(
      "aria-label",
      t("results.duration_aria", { factor: formatNumber(analysis.whole_day.load_factor * 100, lang, 0) }),
    );
    canvases.monthly.setAttribute(
      "aria-label",
      t("results.monthly_aria", { total: formatEnergy(analysis.annual_energy_kwh, lang) }),
    );
    draw(analysis, lang);
  }

  return { render };
}
