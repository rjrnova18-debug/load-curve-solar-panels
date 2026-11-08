// Study files: the whole session saved as JSON in the browser (the app keeps no
// state on the server, see ADR 0001). Pure functions, so they are unit-tested.
//
// File shape (version 1):
//   { "format": "load-curve-study", "version": 1, "saved_at": "...",
//     "study": <the Study the API accepts>, "location": <where its sun hours came from> }

import { emptyStudy, initialState, MONTHS } from "./state.js";

export const STUDY_FILE_FORMAT = "load-curve-study";
export const STUDY_FILE_VERSION = 1;

export class StudyFileError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

/** The JSON text of a study file for the current state. */
export function serializeStudy(state, now = new Date()) {
  const { latitude, longitude, lookup, source } = state.location;
  return JSON.stringify(
    {
      format: STUDY_FILE_FORMAT,
      version: STUDY_FILE_VERSION,
      saved_at: now.toISOString(),
      study: state.study,
      location: { latitude, longitude, lookup, source },
    },
    null,
    2,
  );
}

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/**
 * Read a study file into { study, location } ready for the store.
 *
 * Only the shape is checked here; the values (powers, schedules, ranges) are
 * validated by the API on the next analysis, like any other edit. Missing
 * settings or assumptions fall back to their defaults.
 * Throws StudyFileError: json_invalid, study_file_invalid or study_file_newer.
 */
export function parseStudyFile(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new StudyFileError("json_invalid");
  }
  if (!isObject(data) || data.format !== STUDY_FILE_FORMAT || !isObject(data.study)) {
    throw new StudyFileError("study_file_invalid");
  }
  if (typeof data.version !== "number" || data.version > STUDY_FILE_VERSION) {
    throw new StudyFileError("study_file_newer");
  }

  const defaults = emptyStudy();
  const { study } = data;
  if (!isObject(study.load_table) || !Array.isArray(study.load_table.loads)) {
    throw new StudyFileError("study_file_invalid");
  }
  const settings = isObject(study.settings) ? study.settings : {};
  const multipliers = settings.seasonal_multipliers;
  const solar = study.solar_resource;
  if (solar !== null && solar !== undefined && !(isObject(solar) && Array.isArray(solar.peak_sun_hours))) {
    throw new StudyFileError("study_file_invalid");
  }

  const location = isObject(data.location) ? data.location : {};
  return {
    study: {
      load_table: { loads: study.load_table.loads },
      settings: {
        daytime_window: isObject(settings.daytime_window)
          ? settings.daytime_window
          : defaults.settings.daytime_window,
        seasonal_multipliers:
          Array.isArray(multipliers) && multipliers.length === MONTHS
            ? multipliers
            : defaults.settings.seasonal_multipliers,
      },
      solar_resource: solar ?? null,
      assumptions: { ...defaults.assumptions, ...(isObject(study.assumptions) ? study.assumptions : {}) },
    },
    location: {
      ...initialState().location,
      latitude: typeof location.latitude === "number" ? location.latitude : null,
      longitude: typeof location.longitude === "number" ? location.longitude : null,
      lookup: isObject(location.lookup) ? location.lookup : null,
      source: location.source === "pvgis" || location.source === "manual" ? location.source : null,
    },
  };
}
