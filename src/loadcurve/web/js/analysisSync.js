// Keeps the analysis result in step with the Study. The analyse function is
// injected, so the timing rules can be tested without a server.

import { ApiError } from "./api.js";
import { isAnalysable } from "./state.js";

/**
 * Every change to the Study schedules one analysis after delayMs; a newer change
 * cancels the pending one, and an answer to an older request is ignored. A Study
 * that cannot be analysed clears the result at once.
 *
 * Returns the function that stops listening.
 */
export function keepResultInSync(store, analyse, delayMs) {
  let lastStudy = null;
  let timer = null;
  let latestRequest = 0;

  return store.subscribe((state) => {
    if (state.study === lastStudy) return;
    lastStudy = state.study;
    clearTimeout(timer);
    latestRequest += 1; // answers to anything already sent are now stale
    if (!isAnalysable(state.study)) {
      store.update({ result: null, status: "idle", error: null });
      return;
    }
    timer = setTimeout(async () => {
      const request = ++latestRequest;
      store.update({ status: "loading" });
      try {
        const result = await analyse(state.study);
        if (request === latestRequest) store.update({ result, status: "idle", error: null });
      } catch (error) {
        if (request !== latestRequest) return;
        store.update({ status: "error", error: error instanceof ApiError ? error : new ApiError("generic") });
      }
    }, delayMs);
  });
}
