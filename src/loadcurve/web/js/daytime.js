// The Daytime window rule, once for the whole frontend. It mirrors DaytimeWindow
// in src/loadcurve/domain/models.py; tests/fixtures/daytime_cases.json holds the
// cases both implementations are tested against.
//
// Day runs from start_hour (included) to end_hour (excluded) and may cross
// midnight; every other hour is night.

import { HOURS } from "./state.js";

/** Hours from start up to, but not including, end, wrapping past midnight. */
function hoursBetween(start, end) {
  const length = (end - start + HOURS) % HOURS;
  return Array.from({ length }, (_, offset) => (start + offset) % HOURS);
}

/** Daytime hours in chronological order, starting at start_hour. */
export function daytimeHours({ start_hour: start, end_hour: end }) {
  return hoursBetween(start, end);
}

/** Night-time hours in chronological order, starting at end_hour. */
export function nighttimeHours({ start_hour: start, end_hour: end }) {
  return hoursBetween(end, start);
}

export function isDaytime({ start_hour: start, end_hour: end }, hour) {
  return (hour - start + HOURS) % HOURS < (end - start + HOURS) % HOURS;
}
