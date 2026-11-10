// Step 3: the Solar resource. PVGIS fills the twelve monthly Peak sun hours from a
// location; the same twelve inputs can be typed by hand. Either way, those inputs
// are the Study's solar_resource.

import { lookupSolarResource } from "../api.js";
import { describeError } from "../errors.js";
import { formatNumber } from "../format.js";
import { language, t } from "../i18n.js";
import { MONTHS } from "../state.js";
import { createMonthGrid } from "./monthGrid.js";

const DEFAULT_PEAK_SUN_HOURS = 4.5;
const MAX_PEAK_SUN_HOURS = 12;
const RETRYABLE = new Set(["pvgis_unavailable", "network"]);

export function createLocation(root, store) {
  const latInput = root.querySelector("[data-lat]");
  const lonInput = root.querySelector("[data-lon]");
  const lookupButton = root.querySelector('[data-action="lookup"]');
  const geoButton = root.querySelector('[data-action="geolocate"]');
  const manualButton = root.querySelector('[data-action="manual-psh"]');
  const status = root.querySelector("[data-location-status]");
  const alert = root.querySelector("[data-location-alert]");
  const alertText = root.querySelector("[data-location-alert-text]");
  const retryButton = root.querySelector('[data-action="retry-lookup"]');
  const panel = root.querySelector("[data-psh]");
  const summary = root.querySelector("[data-psh-summary]");
  const sameForAll = root.querySelector("[data-psh-all]");

  const location = () => store.get().location;
  const updateLocation = (patch) => store.update((state) => ({ location: { ...state.location, ...patch } }));

  function saveSunHours(values, source) {
    store.update((state) => ({
      study: { ...state.study, solar_resource: { peak_sun_hours: values } },
      location: { ...state.location, source },
    }));
  }

  const grid = createMonthGrid(root.querySelector("[data-psh-grid]"), {
    min: 0,
    max: MAX_PEAK_SUN_HOURS,
    step: 0.1,
    full: 8, // sunny deserts reach about 7-8 peak sun hours
    onChange: (values) => saveSunHours(values, "manual"),
  });

  function readCoordinate(input, limit) {
    const value = Number(input.value);
    const valid = input.value.trim() !== "" && Number.isFinite(value) && Math.abs(value) <= limit;
    input.setAttribute("aria-invalid", String(!valid));
    return valid ? value : null;
  }

  async function lookup() {
    const latitude = readCoordinate(latInput, 90);
    const longitude = readCoordinate(lonInput, 180);
    if (latitude === null || longitude === null) {
      updateLocation({ status: "error", error: { code: "coordinates_out_of_range" } });
      return;
    }
    updateLocation({ latitude, longitude, status: "loading", error: null });
    try {
      const result = await lookupSolarResource(latitude, longitude);
      store.update((state) => ({
        study: { ...state.study, solar_resource: result.solar_resource },
        location: { ...state.location, status: "idle", lookup: result, source: "pvgis" },
      }));
    } catch (error) {
      updateLocation({ status: "error", error });
    }
  }

  lookupButton.addEventListener("click", lookup);
  retryButton.addEventListener("click", lookup);
  // Typed coordinates belong to the state as soon as the field is left, so a
  // saved study keeps them even without a PVGIS lookup.
  for (const [input, key, limit] of [
    [latInput, "latitude", 90],
    [lonInput, "longitude", 180],
  ]) {
    input.addEventListener("change", () => {
      const value = Number(input.value);
      const valid = input.value.trim() !== "" && Number.isFinite(value) && Math.abs(value) <= limit;
      shownCoordinates.set(input, valid ? value : null);
      updateLocation({ [key]: valid ? value : null });
    });
  }
  for (const input of [latInput, lonInput]) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") lookup();
    });
  }

  geoButton.hidden = !("geolocation" in navigator);
  geoButton.addEventListener("click", () => {
    updateLocation({ status: "locating", error: null });
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        latInput.value = coords.latitude.toFixed(4);
        lonInput.value = coords.longitude.toFixed(4);
        lookup();
      },
      () => updateLocation({ status: "error", error: { code: "geolocation_denied" } }),
      { timeout: 15000 },
    );
  });

  manualButton.addEventListener("click", () => {
    const current = store.get().study.solar_resource;
    saveSunHours(current?.peak_sun_hours ?? Array(MONTHS).fill(DEFAULT_PEAK_SUN_HOURS), "manual");
    panel.querySelector("input")?.focus();
  });

  sameForAll.addEventListener("change", () => {
    const hours = Number(sameForAll.value);
    if (sameForAll.value.trim() === "" || Number.isNaN(hours)) return;
    saveSunHours(Array(MONTHS).fill(Math.min(MAX_PEAK_SUN_HOURS, Math.max(0, hours))), "manual");
    sameForAll.value = "";
  });

  const shownCoordinates = new Map([
    [latInput, null],
    [lonInput, null],
  ]);

  function render(state) {
    const lang = language();
    const { status: lookupStatus, error, lookup: found, source } = state.location;
    const solar = state.study.solar_resource;

    // Write coordinates only when the state's value changed (an opened study, a
    // geolocation), so what the user is typing is never overwritten.
    for (const [input, value] of [
      [latInput, state.location.latitude],
      [lonInput, state.location.longitude],
    ]) {
      if (shownCoordinates.get(input) === value || document.activeElement === input) continue;
      shownCoordinates.set(input, value);
      input.value = value === null ? "" : String(value);
    }

    const busy = lookupStatus === "loading" || lookupStatus === "locating";
    lookupButton.disabled = busy;
    geoButton.disabled = busy;
    status.textContent = busy ? t(`location.${lookupStatus}`) : "";

    alert.hidden = lookupStatus !== "error";
    if (lookupStatus === "error") alertText.textContent = describeError(error);
    retryButton.hidden = !(lookupStatus === "error" && RETRYABLE.has(error?.code));

    panel.hidden = !solar;
    manualButton.hidden = Boolean(solar);
    if (!solar) return;

    grid.render(solar.peak_sun_hours, lang);
    const average = solar.peak_sun_hours.reduce((sum, value) => sum + value, 0) / MONTHS;
    const parts = [t("location.average", { hours: formatNumber(average, lang, 1) })];
    if (source === "pvgis" && found) {
      parts.push(
        t("location.from_pvgis", {
          slope: formatNumber(found.optimal_slope_deg, lang, 0),
          azimuth: formatNumber(found.optimal_azimuth_deg, lang, 0),
        }),
      );
      if (found.horizon_shading === false) parts.push(t("location.no_horizon"));
    } else {
      parts.push(t("location.typed_by_hand"));
    }
    summary.textContent = parts.join(" ");
  }

  return { render, location };
}
