// The single source of truth of the page. Views never change the DOM of other
// views: they update the store, and every subscriber re-renders from the new
// state (the same idea as one setLed() owning an LED in firmware).

export const HOURS = 24;
export const MONTHS = 12;

/** A Study with nothing entered yet; the same JSON shape the API accepts. */
export function emptyStudy() {
  return {
    load_table: { loads: [] },
    settings: {
      daytime_window: { start_hour: 6, end_hour: 18 },
      seasonal_multipliers: Array(MONTHS).fill(1),
    },
    solar_resource: null,
    assumptions: {
      performance_ratio: 0.75,
      panel_power_w: 550,
      battery_depth_of_discharge: 0.8,
      battery_efficiency: 0.95,
      inverter_safety_factor: 1.25,
      days_of_autonomy: 1,
      on_grid_coverage: 1,
    },
  };
}

export function initialState() {
  return {
    study: emptyStudy(),
    result: null, // last StudyResult from the API
    status: "idle", // "idle" | "loading" | "error"
    error: null, // translated by the views from an error code
    // Where the Solar resource came from. Not part of the Study the API receives.
    location: {
      latitude: null,
      longitude: null,
      status: "idle", // "idle" | "locating" | "loading" | "error"
      error: null,
      lookup: null, // last PVGIS answer: optimal slope, azimuth, elevation
      source: null, // "pvgis" | "manual"
    },
  };
}

export function createStore(state = initialState()) {
  const listeners = new Set();
  return {
    get: () => state,
    /** Replace part of the state; an updater function receives the current state. */
    update(change) {
      const patch = typeof change === "function" ? change(state) : change;
      state = { ...state, ...patch };
      for (const listener of listeners) listener(state);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Whether the Study has enough to ask the API for an analysis. */
export function isAnalysable(study) {
  return study.load_table.loads.length > 0;
}
