// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Arithmetic over numbers and series, for the model to compute with instead of working figures out in
 * its head. A small recursive-descent evaluator: numbers, named values, + - * / ^, unary minus,
 * parentheses, lists (`[a / b, c / d]`, several figures at once), indexing (`closes[-1]` counts from
 * the end) and slicing (`closes[-20:]`, as in Python) and a fixed set of functions. Nothing is
 * executed: an expression can only combine the values it is given.
 */

/** A number, or a series whose missing values (null) functions leave out and indexing reports. */
export type Value = number | readonly (number | null)[];

type Token =
  | { kind: "number"; value: number }
  | { kind: "name"; value: string }
  | { kind: "op"; value: string };

class ExpressionError extends Error {}

/** The names series were given under, for messages about them. */
const named = new WeakMap<readonly (number | null)[], string>();

const FUNCTIONS: Record<string, (args: Value[]) => number> = {
  abs: one(Math.abs),
  sqrt: one(Math.sqrt),
  ln: one(Math.log),
  log: one(Math.log10),
  exp: one(Math.exp),
  round: (args) => {
    const [x, digits = 0] = scalars("round", args, 1, 2) as [number, number?];
    const scale = 10 ** digits;
    return Math.round(x * scale) / scale;
  },
  pct_change: (args) => {
    const [from, to] = scalars("pct_change", args, 2, 2) as [number, number];
    if (from === 0) throw new ExpressionError("pct_change: division by zero (the first value is 0)");
    return (to / from - 1) * 100;
  },
  min: (args) => Math.min(...flat("min", args)),
  max: (args) => Math.max(...flat("max", args)),
  sum: (args) => flat("sum", args).reduce((a, b) => a + b, 0),
  mean: (args) => {
    const xs = flat("mean", args);
    return xs.reduce((a, b) => a + b, 0) / xs.length;
  },
  stdev: (args) => {
    const xs = flat("stdev", args);
    if (xs.length < 2) throw new ExpressionError("stdev needs at least 2 values");
    return Math.sqrt(sampleVariance(xs));
  },
  var: (args) => {
    const xs = flat("var", args);
    if (xs.length < 2) throw new ExpressionError("var needs at least 2 values");
    return sampleVariance(xs);
  },
  median: (args) => quantile(flat("median", args), 0.5),
  percentile: (args) => {
    const p = args.at(-1);
    if (args.length < 2 || typeof p !== "number")
      throw new ExpressionError("percentile takes the values and then p, such as percentile(closes, 90)");
    if (p < 0 || p > 100) throw new ExpressionError(`percentile: p is from 0 to 100, not ${p}`);
    return quantile(flat("percentile", args.slice(0, -1)), p / 100);
  },
  skew: (args) => {
    const xs = flat("skew", args);
    const n = xs.length;
    if (n < 3) throw new ExpressionError("skew needs at least 3 values");
    return (n / ((n - 1) * (n - 2))) * standardizedSum(xs, 3);
  },
  kurt: (args) => {
    const xs = flat("kurt", args);
    const n = xs.length;
    if (n < 4) throw new ExpressionError("kurt needs at least 4 values");
    return (
      ((n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3))) * standardizedSum(xs, 4) -
      (3 * (n - 1) ** 2) / ((n - 2) * (n - 3))
    );
  },
  count: (args) => flat("count", args).length,
  first: (args) => series("first", args)[0] as number,
  last: (args) => series("last", args).at(-1) as number,
};

/**
 * The value of `expression` over `values`, or what is wrong with it: one number, or a list of them
 * (a list written as one, or a series). Never throws.
 */
export function evaluate(
  expression: string,
  values: Readonly<Record<string, Value>>,
): { value: Value } | { error: string } {
  try {
    const parser = new Parser(tokenize(expression), values);
    const value = parser.expression();
    parser.end();
    return { value: typeof value === "number" ? finite(value) : value };
  } catch (error) {
    if (error instanceof ExpressionError) return { error: error.message };
    throw error;
  }
}

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  const pattern =
    /\s*(?:(\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(\S))/y;
  for (;;) {
    const at = pattern.lastIndex;
    const match = pattern.exec(text);
    if (!match) {
      if (text.slice(at).trim()) throw new ExpressionError(`cannot read "${text.slice(at).trim()}"`);
      return tokens;
    }
    const [, number, name, op] = match;
    if (number !== undefined) tokens.push({ kind: "number", value: Number(number) });
    else if (name !== undefined) tokens.push({ kind: "name", value: name });
    else if (op !== undefined) {
      if (!"+-*/^()[],:".includes(op)) throw new ExpressionError(`unexpected "${op}"`);
      tokens.push({ kind: "op", value: op });
    }
  }
}

class Parser {
  private at = 0;

  constructor(
    private readonly tokens: Token[],
    private readonly values: Readonly<Record<string, Value>>,
  ) {}

  end(): void {
    const token = this.tokens[this.at];
    if (token) throw new ExpressionError(`unexpected "${token.value}"`);
  }

  expression(): Value {
    let left = this.term();
    while (this.peek("+") || this.peek("-")) {
      const op = this.next().value;
      const right = this.term();
      left = op === "+" ? scalar(left, "+") + scalar(right, "+") : scalar(left, "-") - scalar(right, "-");
    }
    return left;
  }

  private term(): Value {
    let left = this.unary();
    while (this.peek("*") || this.peek("/")) {
      const op = this.next().value;
      const right = this.unary();
      if (op === "*") left = scalar(left, "*") * scalar(right, "*");
      else {
        const divisor = scalar(right, "/");
        if (divisor === 0) throw new ExpressionError("division by zero");
        left = scalar(left, "/") / divisor;
      }
    }
    return left;
  }

  private unary(): Value {
    if (this.peek("-")) {
      this.next();
      return -scalar(this.unary(), "-");
    }
    if (this.peek("+")) {
      this.next();
      return scalar(this.unary(), "+");
    }
    return this.power();
  }

  private power(): Value {
    const base = this.postfix();
    if (!this.peek("^")) return base;
    this.next();
    return finite(scalar(base, "^") ** scalar(this.unary(), "^"));
  }

  private postfix(): Value {
    let value = this.primary();
    while (this.peek("[")) {
      this.next();
      // An index ([-1]) or a slice ([-20:], [:5], [2:10]), as in Python: the end is left out.
      const start = this.peek(":") ? undefined : scalar(this.expression(), "[]");
      if (!this.peek(":")) {
        this.expect("]");
        value = indexed(value, start as number);
        continue;
      }
      this.next();
      const end = this.peek("]") || this.peek(":") ? undefined : scalar(this.expression(), "[]");
      if (this.peek(":"))
        throw new ExpressionError(
          "a slice takes a start and an end only, such as closes[-20:]; a step is not supported",
        );
      this.expect("]");
      value = sliced(value, start, end);
    }
    return value;
  }

  private primary(): Value {
    const token = this.next();
    if (token.kind === "number") return token.value;
    if (token.kind === "name") {
      if (this.peek("(")) {
        this.next();
        const args: Value[] = [];
        if (!this.peek(")")) {
          do args.push(this.expression());
          while (this.peek(",") && this.next());
        }
        this.expect(")");
        const fn = FUNCTIONS[token.value];
        if (!fn) {
          throw new ExpressionError(
            `there is no function named ${token.value}; there are ${Object.keys(FUNCTIONS).join(", ")}`,
          );
        }
        return finite(fn(args));
      }
      const value = this.values[token.value];
      if (value === undefined) {
        const names = Object.keys(this.values);
        throw new ExpressionError(
          `there is no value named ${token.value}${names.length ? `; the values are ${names.join(", ")}` : ""}`,
        );
      }
      if (typeof value !== "number") named.set(value, token.value);
      return value;
    }
    if (token.value === "(") {
      const value = this.expression();
      this.expect(")");
      return value;
    }
    // A list of figures, each one number: [a / b * 100, c / d * 100].
    if (token.value === "[") {
      const items: number[] = [];
      if (!this.peek("]")) {
        do {
          const item = this.expression();
          if (typeof item !== "number")
            throw new ExpressionError(
              "a list's items are single numbers, such as [a / b, c / d]; for a series inside one, use sum, mean, last or an index",
            );
          items.push(finite(item));
        } while (this.peek(",") && this.next());
      }
      this.expect("]");
      return items;
    }
    throw new ExpressionError(`unexpected "${token.value}"`);
  }

  private peek(op: string): boolean {
    const token = this.tokens[this.at];
    return token?.kind === "op" && token.value === op;
  }

  private next(): Token {
    const token = this.tokens[this.at++];
    if (!token) throw new ExpressionError("the end of the expression came too soon");
    return token;
  }

  private expect(op: string): void {
    const token = this.next();
    if (token.kind !== "op" || token.value !== op)
      throw new ExpressionError(`expected "${op}", found "${token.value}"`);
  }
}

function scalar(value: Value, op: string): number {
  if (typeof value === "number") return value;
  throw new ExpressionError(
    `${named.get(value) ?? "a value"} is a series of ${value.length} values and cannot take "${op}": use sum, mean, last or an index such as [0]`,
  );
}

function indexed(value: Value, index: number): number {
  if (typeof value === "number") throw new ExpressionError(`${value} is one number, not a series to index`);
  const name = named.get(value) ?? "the series";
  const at = index < 0 ? value.length + index : index;
  if (!Number.isInteger(index) || at < 0 || at >= value.length) {
    throw new ExpressionError(`index ${index} is outside ${name} (${value.length} values)`);
  }
  const item = value[at];
  if (item === null || item === undefined) throw new ExpressionError(`${name}[${index}] has no value`);
  return item;
}

/** The values from `start` up to `end` (left out), counting from the end when negative, as in Python. */
function sliced(value: Value, start: number | undefined, end: number | undefined): Value {
  if (typeof value === "number") throw new ExpressionError(`${value} is one number, not a series to slice`);
  for (const bound of [start, end]) {
    if (bound !== undefined && !Number.isInteger(bound))
      throw new ExpressionError(`a slice's bounds are whole numbers, not ${bound}`);
  }
  const part = value.slice(start, end);
  if (!part.length) {
    throw new ExpressionError(
      `the slice [${start ?? ""}:${end ?? ""}] of ${named.get(value) ?? "the series"} (${value.length} values) is empty`,
    );
  }
  named.set(part, `${named.get(value) ?? "the series"}[${start ?? ""}:${end ?? ""}]`);
  return part;
}

function finite(value: number): number {
  if (!Number.isFinite(value)) throw new ExpressionError("the result is not a finite number");
  return value;
}

function one(fn: (x: number) => number): (args: Value[]) => number {
  return (args) => fn(...(scalars("function", args, 1, 1) as [number]));
}

function scalars(name: string, args: Value[], least: number, most: number): number[] {
  if (args.length < least || args.length > most) {
    throw new ExpressionError(`${name} takes ${least === most ? least : `${least} to ${most}`} values`);
  }
  return args.map((arg) => scalar(arg, name));
}

function flat(name: string, args: Value[]): number[] {
  const xs = args.flatMap((arg) =>
    typeof arg === "number" ? [arg] : arg.filter((x): x is number => x !== null),
  );
  if (!xs.length) throw new ExpressionError(`${name} needs at least one value`);
  return xs;
}

function series(name: string, args: Value[]): readonly number[] {
  const [only] = args;
  const present = typeof only === "object" ? only.filter((x): x is number => x !== null) : [];
  if (args.length !== 1 || !present.length) throw new ExpressionError(`${name} takes one series with values`);
  return present;
}

/** The sample variance: squared deviations from the mean over n - 1; exactly 0 when every value is the same. */
function sampleVariance(xs: readonly number[]): number {
  // The mean of repeated decimals can round off the value itself, which would leave a tiny spread.
  if (xs.every((x) => x === xs[0])) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  return xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (xs.length - 1);
}

/**
 * The q-quantile (q from 0 to 1) by linear interpolation between the sorted values: at position
 * q * (n - 1), counting from 0. This is numpy's default and the spreadsheet PERCENTILE.INC.
 */
function quantile(xs: readonly number[], q: number): number {
  const sorted = [...xs].sort((a, b) => a - b);
  const at = q * (sorted.length - 1);
  const below = Math.floor(at);
  const low = sorted[below] as number;
  const high = sorted[Math.min(below + 1, sorted.length - 1)] as number;
  return low + (high - low) * (at - below);
}

/**
 * The sum of each value's deviation from the mean over the sample standard deviation, raised to
 * `power`: the core of the sample-adjusted skewness and excess kurtosis (the spreadsheet SKEW and KURT).
 */
function standardizedSum(xs: readonly number[], power: number): number {
  const sd = Math.sqrt(sampleVariance(xs));
  if (sd === 0) throw new ExpressionError("the values do not vary, so their shape is not defined");
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  return xs.reduce((a, b) => a + ((b - mean) / sd) ** power, 0);
}
