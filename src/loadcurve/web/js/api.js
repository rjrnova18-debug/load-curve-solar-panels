// Calls to the backend. Every failure becomes an ApiError with a stable code
// (see the README): views translate it with t(`errors.${code}`).

export class ApiError extends Error {
  constructor(code, details = {}) {
    super(code);
    this.code = code;
    this.details = details;
  }
}

/** Read the error code (and its context) from a FastAPI error body. */
export function parseErrorBody(body) {
  const detail = body?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // 422 request validation: Pydantic's error type is the code.
    const [first] = detail;
    return { code: first.type ?? "generic", details: { ...first.ctx, location: first.loc } };
  }
  if (detail && typeof detail === "object" && detail.code) {
    const { code, ...details } = detail;
    return { code, details };
  }
  return { code: "generic", details: {} };
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError("network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const { code, details } = parseErrorBody(body);
    throw new ApiError(code, details);
  }
  return response;
}

function postJson(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** The Load analysis of a Study, plus System sizings when it has a Solar resource. */
export async function analyseStudy(study) {
  return (await postJson("/api/analysis", study)).json();
}

/** Parse a CSV/XLSX file into { loads, issues }. */
export async function importLoadTable(file) {
  const form = new FormData();
  form.append("file", file);
  return (await request("/api/load-table/import", { method: "POST", body: form })).json();
}

/** The sample office, read through the same import path a user's file takes. */
export async function sampleLoads() {
  const template = await (await request("/api/load-table/template?format=csv")).blob();
  const result = await importLoadTable(new File([template], "template.csv"));
  return result.loads;
}

export async function lookupSolarResource(latitude, longitude) {
  const query = new URLSearchParams({ lat: latitude, lon: longitude });
  return (await request(`/api/solar-resource?${query}`)).json();
}

/** POST a JSON body and save the file the server returns. */
export async function downloadFile(path, payload, filename) {
  const blob = await (await postJson(path, payload)).blob();
  saveBlob(blob, filename);
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
