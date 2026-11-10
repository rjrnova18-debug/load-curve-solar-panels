// Calculation steps (expression trees from the sizing module) drawn as MathML,
// which browsers render natively as real formulas: fractions with a numerator
// and a denominator, subscripts, ceiling brackets. The Excel report draws the
// same trees as text (src/loadcurve/files/formula_text.py).
//
// Pure: what a symbol looks like and how numbers are written are passed in, so
// the module needs no DOM and no translations.
//
//   options.symbol(key, qualifier) -> { base: "E", sub: "day" }   (sub may be "")
//   options.number(value)          -> "156.08"

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
const escape = (text) => String(text).replace(/[&<>"]/g, (char) => ESCAPES[char]);

const mn = (text) => `<mn>${escape(text)}</mn>`;
const mo = (text) => `<mo>${escape(text)}</mo>`;

function symbolMarkup({ base, sub }) {
  const identifier = `<mi>${escape(base)}</mi>`;
  return sub ? `<msub>${identifier}<mtext>${escape(sub)}</mtext></msub>` : identifier;
}

function quantityMarkup(number, unit) {
  return unit ? `${mn(number)}<mspace width="0.2em"></mspace><mtext>${escape(unit)}</mtext>` : mn(number);
}

/** An expression as MathML, with symbols (numbers: false) or with its values. */
export function expressionMathML(expression, { numbers, symbol, number }) {
  const draw = (node) => {
    switch (node.kind) {
      case "value":
        if (node.symbol === null) return mn(number(node.value));
        return numbers ? quantityMarkup(number(node.value), node.unit) : symbolMarkup(symbol(node.symbol, node.qualifier));
      case "product":
        return node.terms.map(inProduct).join(mo("×"));
      case "fraction":
        return `<mfrac><mrow>${draw(node.numerator)}</mrow><mrow>${draw(node.denominator)}</mrow></mfrac>`;
      case "sum":
        return node.terms.map(draw).join(mo("+"));
      case "ceiling":
        return `<mrow>${mo("⌈")}${draw(node.argument)}${mo("⌉")}</mrow>`;
      default:
        throw new TypeError(`Unknown expression kind: ${node.kind}`);
    }
  };
  // A sum multiplied by something needs parentheses; a fraction draws its own bar.
  const inProduct = (node) => (node.kind === "sum" ? `<mrow>${mo("(")}${draw(node)}${mo(")")}</mrow>` : draw(node));
  return draw(expression);
}

/**
 * A calculation step as two block formulas:
 *   result symbol = formula with symbols
 *   result symbol = formula with numbers = result
 */
export function stepMathML(step, { symbol, number, label }) {
  const left = `${symbolMarkup(symbol(step.quantity, null))}${mo("=")}`;
  const symbolic = expressionMathML(step.expression, { numbers: false, symbol, number });
  const numeric = expressionMathML(step.expression, { numbers: true, symbol, number });
  const result = quantityMarkup(number(step.result), step.unit);
  const math = (body) => `<math display="block" aria-label="${escape(label)}">${body}</math>`;
  return {
    symbolic: math(`${left}${symbolic}`),
    numeric: math(`${left}${numeric}${mo("=")}${result}`),
  };
}

/** Every distinct (symbol, qualifier) a step uses, in reading order, for the legend. */
export function symbolsUsed(expression) {
  const found = new Map();
  const visit = (node) => {
    if (node.kind === "value") {
      if (node.symbol !== null) found.set(`${node.symbol}|${node.qualifier ?? ""}`, { key: node.symbol, qualifier: node.qualifier });
      return;
    }
    const children =
      node.kind === "fraction" ? [node.numerator, node.denominator] : node.kind === "ceiling" ? [node.argument] : node.terms;
    children.forEach(visit);
  };
  visit(expression);
  return [...found.values()];
}
