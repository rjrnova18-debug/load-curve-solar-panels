// Turn an error code (from the API, an import issue or the network) into a message.

import { t } from "./i18n.js";

/** Pick the message key for a code: "<code>_plain" when the limit it mentions is unknown. */
export function messageKey(code, details, hasKey) {
  const limit = details.gt ?? details.ge ?? details.lt ?? details.le;
  if (limit === undefined && hasKey(`errors.${code}_plain`)) return `errors.${code}_plain`;
  return hasKey(`errors.${code}`) ? `errors.${code}` : "errors.generic";
}

/** A user-facing message for { code, details }. */
export function describeError({ code, details = {} }) {
  const hasKey = (key) => t(key) !== key;
  const vars = {
    ...details,
    limit: details.gt ?? details.ge ?? details.lt ?? details.le,
    columns: (details.columns ?? []).join(", "),
  };
  return t(messageKey(code, details, hasKey), vars);
}
