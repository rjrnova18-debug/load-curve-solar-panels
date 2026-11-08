// The 24-hour sky: the hourly profile drawn as the skyline of a solarpunk city.
// Each building is one hour; its height is the power drawn in that hour. The sun
// travels across the daytime window, and night-time hours get stars and lit windows.
//
// The scene is built once; render() only moves and recolours it, so edits animate.

import { formatEnergy, formatHour, formatPercent, formatPower } from "../format.js";
import { language, t } from "../i18n.js";
import { HOURS } from "../state.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const WIDTH = 1200;
const HEIGHT = 360;
const GROUND = 330;
const COLUMN = WIDTH / HOURS; // 50
const BUILDING_WIDTH = 38;
const BUILDING_INSET = (COLUMN - BUILDING_WIDTH) / 2;
const TALLEST = 230;
const SHORTEST = 18;
const BURIED = TALLEST + 40; // translateY that hides a building below the ground
const HORIZON = 250;
const APEX = 50;
// Cubic control height that makes the arc peak exactly at APEX.
const ARC_CONTROL = HORIZON + (APEX - HORIZON) / 0.75;
const INTRO_MS = 1200;

// A gentle silhouette shown before there is any data.
const PLACEHOLDER = [
  0.18, 0.16, 0.15, 0.15, 0.17, 0.24, 0.36, 0.42, 0.5, 0.56, 0.6, 0.62, 0.58, 0.6, 0.57, 0.52,
  0.5, 0.55, 0.62, 0.58, 0.48, 0.36, 0.26, 0.2,
];

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function svg(name, attributes = {}, parent = null) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (parent) parent.append(element);
  return element;
}

/** Point on a cubic Bézier curve at parameter t. */
function bezier(p0, p1, p2, p3, t) {
  const u = 1 - t;
  return u ** 3 * p0 + 3 * u ** 2 * t * p1 + 3 * u * t ** 2 * p2 + t ** 3 * p3;
}

function sunArc(startHour, endHour) {
  const x0 = startHour * COLUMN;
  const x1 = (endHour <= startHour ? endHour + HOURS : endHour) * COLUMN;
  const span = x1 - x0;
  return { x: [x0, x0 + 0.3 * span, x1 - 0.3 * span, x1], y: [HORIZON, ARC_CONTROL, ARC_CONTROL, HORIZON] };
}

function arcPoint(arc, t) {
  const x = bezier(...arc.x, t) % WIDTH;
  return { x, y: bezier(...arc.y, t) };
}

function arcPath(arc) {
  const [x0, x1, x2, x3] = arc.x;
  const [y0, y1, y2, y3] = arc.y;
  return `M${x0} ${y0} C${x1} ${y1} ${x2} ${y2} ${x3} ${y3}`;
}

// ---------- Scene pieces ----------

function buildingShape(kind) {
  const w = BUILDING_WIDTH;
  const top = -TALLEST;
  if (kind === 0) return `M0 0 V${top + 10} Q${w / 2} ${top - 16} ${w} ${top + 10} V0 Z`; // arched
  if (kind === 1) return `M0 0 V${top} H${w} V0 Z`; // flat roof garden
  return `M0 0 V${top + 4} L${w / 2} ${top - 12} L${w} ${top + 4} V0 Z`; // gabled
}

function addRoof(group, kind) {
  const top = -TALLEST;
  if (kind === 1) {
    for (const [cx, rx] of [
      [9, 7],
      [20, 8],
      [31, 6],
    ]) {
      svg("ellipse", { class: "leaf", cx, cy: top - 4, rx, ry: 6 }, group);
    }
  } else if (kind === 0) {
    svg("path", { class: "roof-panel", d: `M22 ${top - 2} l12 -5 v6 l-12 5 Z` }, group);
  } else {
    svg("path", { class: "leaf", d: `M8 ${top + 2} q4 -14 8 0 Z` }, group);
  }
}

function addWindmill(group) {
  const mill = svg("g", { class: "windmill", transform: `translate(${BUILDING_WIDTH / 2} ${-TALLEST - 4})` }, group);
  svg("path", { class: "windmill__mast", d: "M-2 0 L-1 -34 H1 L2 0 Z" }, mill);
  const blades = svg("g", { class: "windmill__blades", transform: "translate(0 -34)" }, mill);
  const spin = svg("g", { class: "spin" }, blades);
  for (const angle of [0, 120, 240]) {
    svg("path", { d: "M0 0 C3 -6 3 -18 0 -22 C-3 -18 -3 -6 0 0 Z", transform: `rotate(${angle})` }, spin);
  }
  svg("circle", { class: "windmill__hub", r: 2.5 }, blades);
}

function createBuilding(layer, hour) {
  const column = svg("g", { transform: `translate(${hour * COLUMN + BUILDING_INSET} ${GROUND})` }, layer);
  const rise = svg("g", { class: "rise", style: `--i:${hour}; transform: translateY(${BURIED}px)` }, column);
  const kind = hour % 3;
  svg("path", { class: "building__body", d: buildingShape(kind) }, rise);
  for (let y = -TALLEST + 18; y < -8; y += 16) {
    for (const x of [7, 17, 27]) svg("rect", { class: "window", x, y, width: 5, height: 8, rx: 1 }, rise);
  }
  addRoof(rise, kind);
  addWindmill(rise);
  return { column, rise };
}

function addBalloon(layer, x, y, variant) {
  const balloon = svg("g", { class: `balloon balloon--${variant}`, transform: `translate(${x} ${y})` }, layer);
  const bob = svg("g", { class: "bob" }, balloon);
  svg("path", { class: "balloon__envelope", d: "M0 -30 C20 -30 24 -6 9 10 L-9 10 C-24 -6 -20 -30 0 -30 Z" }, bob);
  svg("path", { class: "balloon__stripe", d: "M0 -30 C7 -24 7 0 3 10 L-3 10 C-7 0 -7 -24 0 -30 Z" }, bob);
  svg("path", { class: "rigging", d: "M-8 10 L-5 20 M8 10 L5 20" }, bob);
  svg("rect", { class: "basket", x: -6, y: 20, width: 12, height: 8, rx: 1.5 }, bob);
}

function addAirship(layer) {
  const ship = svg("g", { class: "airship" }, layer);
  const body = svg("g", { transform: "translate(0 78)" }, ship);
  // It drifts to the left, so the tail fins sit on the right.
  svg("path", { class: "airship__fin", d: "M62 -2 L82 -20 L74 0 L82 20 Z" }, body);
  svg("ellipse", { class: "airship__body", cx: 0, cy: 0, rx: 66, ry: 19 }, body);
  svg("path", { class: "airship__band", d: "M-30 -17 Q-26 0 -30 17 M0 -19 V19 M30 -17 Q26 0 30 17" }, body);
  svg("path", { class: "rigging", d: "M-14 18 L-10 30 M14 18 L10 30" }, body);
  svg("rect", { class: "airship__gondola", x: -14, y: 29, width: 28, height: 9, rx: 3 }, body);
  svg("path", { class: "airship__garden", d: "M-10 29 q3 -7 6 0 q3 -7 6 0 q3 -7 6 0" }, body);
}

function addDrone(layer) {
  const drone = svg("g", { class: "drone", transform: "translate(470 132)" }, layer);
  const hover = svg("g", { class: "hover" }, drone);
  svg("path", { class: "drone__arms", d: "M-18 -2 H18 M-12 -6 L12 2 M12 -6 L-12 2" }, hover);
  for (const x of [-18, 18]) svg("ellipse", { class: "drone__rotor", cx: x, cy: -5, rx: 9, ry: 2 }, hover);
  svg("rect", { class: "drone__body", x: -7, y: -5, width: 14, height: 7, rx: 3 }, hover);
  svg("path", { class: "rigging", d: "M-5 2 L-9 12 M5 2 L9 12" }, hover);
  svg("path", { class: "roof-panel", d: "M-14 12 H14 L10 18 H-10 Z" }, hover);
}

function addStars(layer) {
  const stars = [];
  for (let i = 0; i < 70; i += 1) {
    // Deterministic scatter: the same sky on every visit.
    const x = (i * 173.3 + 37) % WIDTH;
    const y = 12 + ((i * 59.7) % 190);
    stars.push({ x, element: svg("circle", { class: "star", cx: x, cy: y, r: i % 5 === 0 ? 1.6 : 1 }, layer) });
  }
  return stars;
}

// ---------- The view ----------

export function createHero(root) {
  const summary = root.querySelector("[data-hero-summary]");
  const sky = svg("svg", {
    class: "sky is-intro",
    viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    role: "img",
    preserveAspectRatio: "xMidYMid meet",
  });
  root.querySelector("[data-sky]").append(sky);

  const defs = svg("defs", {}, sky);
  const skyGradient = svg("linearGradient", { id: "sky-band", x1: 0, x2: 1, y1: 0, y2: 0 }, defs);
  const haze = svg("linearGradient", { id: "sky-haze", x1: 0, x2: 0, y1: 0, y2: 1 }, defs);
  svg("stop", { offset: 0.35, style: "stop-color: var(--bg); stop-opacity: 0" }, haze);
  svg("stop", { offset: 1, style: "stop-color: var(--bg); stop-opacity: 0.85" }, haze);
  const clip = svg("clipPath", { id: "above-ground" }, defs);
  svg("rect", { x: 0, y: 0, width: WIDTH, height: GROUND }, clip);

  svg("rect", { width: WIDTH, height: GROUND, fill: "url(#sky-band)" }, sky);
  const stars = addStars(svg("g", { class: "stars" }, sky));
  // Crescent: a half circle closed by a flatter arc that bulges the same way.
  const moon = svg("path", { class: "moon", d: "M0 -16 A16 16 0 1 0 0 16 A20 20 0 0 1 0 -16 Z" }, sky);
  const arcLayer = svg("g", { class: "sun-arc" }, sky);
  const arcPaths = [svg("path", {}, arcLayer), svg("path", { transform: `translate(${-WIDTH} 0)` }, arcLayer)];
  const sun = svg("g", { class: "sun" }, sky);
  svg("circle", { class: "sun__glow", r: 44 }, sun);
  svg("circle", { class: "sun__disc", r: 22 }, sun);
  svg("rect", { width: WIDTH, height: GROUND, fill: "url(#sky-haze)" }, sky);

  const city = svg("g", { "clip-path": "url(#above-ground)" }, sky);
  const buildings = Array.from({ length: HOURS }, (_, hour) => createBuilding(city, hour));
  svg("rect", { class: "ground", x: 0, y: GROUND, width: WIDTH, height: HEIGHT - GROUND }, sky);

  // Flying things go in front of the city, in the sky above the tallest building.
  const ambient = svg("g", { class: "ambient" }, sky);
  addAirship(ambient);
  addBalloon(ambient, 205, 118, "sun");
  addBalloon(ambient, 1010, 92, "verdigris");
  addDrone(ambient);

  const hits = Array.from({ length: HOURS }, (_, hour) => {
    const hit = svg("rect", { class: "hit", x: hour * COLUMN, y: 0, width: COLUMN, height: GROUND }, sky);
    return { hit, title: svg("title", {}, hit) };
  });

  // Ambient loops only run while the hero is on screen.
  new IntersectionObserver(([entry]) => sky.classList.toggle("is-paused", !entry.isIntersecting)).observe(sky);

  let introDone = false;
  let sunT = 0.5;

  function placeSun(arc, t) {
    const point = arcPoint(arc, t);
    sun.setAttribute("transform", `translate(${point.x} ${point.y})`);
  }

  function playIntro(arc) {
    introDone = true;
    if (reducedMotion()) {
      placeSun(arc, sunT);
      sky.classList.remove("is-intro");
      return;
    }
    const started = performance.now();
    const frame = (now) => {
      const progress = Math.min(1, (now - started) / INTRO_MS);
      const eased = 1 - (1 - progress) ** 3;
      placeSun(arc, eased * sunT);
      if (progress < 1) requestAnimationFrame(frame);
      else sky.classList.remove("is-intro");
    };
    requestAnimationFrame(frame);
  }

  function paintSky(daytime) {
    skyGradient.replaceChildren();
    for (let hour = 0; hour < HOURS; hour += 1) {
      const color = daytime.has(hour) ? "var(--sky-day-top)" : "var(--sky-night-top)";
      for (const edge of [hour * COLUMN + 14, (hour + 1) * COLUMN - 14]) {
        svg("stop", { offset: edge / WIDTH, style: `stop-color: ${color}` }, skyGradient);
      }
    }
  }

  function render(state) {
    const { start_hour: start, end_hour: end } = state.study.settings.daytime_window;
    const daytime = new Set(Array.from({ length: (end - start + HOURS) % HOURS }, (_, i) => (start + i) % HOURS));
    const night = Array.from({ length: HOURS - daytime.size }, (_, i) => (end + i) % HOURS);
    const analysis = state.result?.analysis ?? null;
    const profile = analysis?.hourly_profile_w ?? null;
    const peak = profile ? Math.max(...profile) : 0;
    const ratios = profile && peak > 0 ? profile.map((watts) => watts / peak) : PLACEHOLDER;
    const lang = language();

    paintSky(daytime);
    sky.classList.toggle("is-placeholder", !profile);

    // Windmills turn on the two calmest hours.
    const calmest = new Set(
      ratios
        .map((ratio, hour) => ({ ratio, hour }))
        .sort((a, b) => a.ratio - b.ratio || a.hour - b.hour)
        .slice(0, 2)
        .map(({ hour }) => hour),
    );

    buildings.forEach(({ column, rise }, hour) => {
      const height = SHORTEST + ratios[hour] * (TALLEST - SHORTEST);
      const target = TALLEST - height;
      // On the first paint the buildings start buried; the next frame raises them.
      requestAnimationFrame(() => {
        rise.style.transform = `translateY(${target}px)`;
      });
      column.classList.toggle("is-night", !daytime.has(hour));
      column.classList.toggle("has-windmill", calmest.has(hour));
    });

    for (const { x, element } of stars) {
      element.classList.toggle("is-night", !daytime.has(Math.floor(x / COLUMN)));
    }
    const moonHour = night[Math.floor(night.length / 3)];
    moon.setAttribute("transform", `translate(${moonHour * COLUMN + COLUMN / 2} 70)`);

    const arc = sunArc(start, end);
    arcPaths.forEach((path) => path.setAttribute("d", arcPath(arc)));
    if (introDone) placeSun(arc, sunT);
    else playIntro(arc);

    hits.forEach(({ title }, hour) => {
      title.textContent = profile
        ? t("hero.hour_power", { hour: formatHour(hour), power: formatPower(profile[hour], lang) })
        : formatHour(hour);
    });

    if (analysis) {
      const { whole_day: day, daytime: dayPart, nighttime: nightPart } = analysis;
      const total = day.energy_kwh || 1;
      sky.setAttribute(
        "aria-label",
        t("hero.aria", {
          peak: formatPower(day.peak_power_w, lang),
          peak_hour: formatHour(day.peak_hour),
          base: formatPower(day.base_power_w, lang),
          base_hour: formatHour(day.base_hour),
        }),
      );
      fillSummary(summary, {
        energy: formatEnergy(day.energy_kwh, lang),
        day: formatPercent(dayPart.energy_kwh / total, lang),
        night: formatPercent(nightPart.energy_kwh / total, lang),
      });
    } else {
      sky.setAttribute("aria-label", t("hero.aria_empty"));
      summary.textContent = t("hero.empty");
    }
  }

  return { render };
}

/** "152.7 kWh a day: 57% by day and 43% at night", with day and night in their colours. */
function fillSummary(element, { energy, day, night }) {
  const byDay = Object.assign(document.createElement("span"), {
    className: "is-day",
    textContent: t("hero.by_day", { share: day }),
  });
  const atNight = Object.assign(document.createElement("span"), {
    className: "is-night",
    textContent: t("hero.at_night", { share: night }),
  });
  const strong = Object.assign(document.createElement("strong"), { textContent: energy });
  const parts = t("hero.summary").split(/(\{energy\}|\{day\}|\{night\})/);
  const nodes = { "{energy}": strong, "{day}": byDay, "{night}": atNight };
  element.replaceChildren(...parts.map((part) => nodes[part] ?? document.createTextNode(part)));
}
