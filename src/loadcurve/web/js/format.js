// Number formatting in the user's language (decimal comma in Spanish).

const LOCALES = { en: "en-US", es: "es-CO" };

function formatter(lang, digits) {
  return new Intl.NumberFormat(LOCALES[lang] ?? lang, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatNumber(value, lang, digits = 0) {
  return formatter(lang, digits).format(value);
}

/** Power with a unit that keeps numbers short: 350 W, 12.4 kW, 1.20 MW. */
export function formatPower(watts, lang) {
  const magnitude = Math.abs(watts);
  if (magnitude >= 1e6) return `${formatNumber(watts / 1e6, lang, 2)} MW`;
  if (magnitude >= 1e3) return `${formatNumber(watts / 1e3, lang, 1)} kW`;
  return `${formatNumber(watts, lang, 0)} W`;
}

/** Energy in kWh, with fewer decimals as values grow. */
export function formatEnergy(kwh, lang) {
  const digits = Math.abs(kwh) >= 1000 ? 0 : Math.abs(kwh) >= 10 ? 1 : 2;
  return `${formatNumber(kwh, lang, digits)} kWh`;
}

export function formatPercent(fraction, lang) {
  return new Intl.NumberFormat(LOCALES[lang] ?? lang, {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(fraction);
}

/** "06:00" style hour label. */
export function formatHour(hour) {
  return `${String(hour).padStart(2, "0")}:00`;
}
