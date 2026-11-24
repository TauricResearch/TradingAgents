// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * References in a tool's arguments, {"ref": "e7", "path": "closes"}: the value at that path of result e7,
 * put in place before the arguments are checked. A path is fields, [N] indexes and [a:b] slices
 * (closes[-1] counts from the end, closes[-20:] is the last 20, periods[0].lines); without one, the whole
 * result. A whole result may be named with a label, {"ref": "e7", "label": "NVDA"}, which the tool shows
 * it by; a label sets no data. A reference that misses says what is there; it never throws.
 */

/** A recorded result's id: e7. */
export const ID = /^e[1-9]\d*$/;
const STEP = String.raw`\[-?\d+\]|\[(?:-?\d+)?:(?:-?\d+)?\]`;
/** A path into a result: fields, [N] indexes and [a:b] slices, such as closes[-20:] or periods[0].lines. */
export const PATH = new RegExp(
  String.raw`^(?:[A-Za-z_][A-Za-z0-9_]*|${STEP})(?:\.[A-Za-z_][A-Za-z0-9_]*|${STEP})*$`,
);
/** The longest name a series, or a result referenced whole, may be given. */
export const NAME_CHARS = 40;

/**
 * Where references read from: a result's payload, or that only its preview was kept (too large to keep with the session), with
 * the run and step that made it.
 */
export type ReferenceSource = {
  /** Whether an id not published yet could still come from this step's calls. */
  pending?(id: string): boolean;
  payload(
    id: string,
  ): (({ payload: unknown } | { localOnly: true }) & { run: string; step: number }) | undefined;
};

/**
 * How a reference to result `id`'s data at `path` ("closes", "periods[0].lines", or none for all of it)
 * is written: the one place the syntax the model reads and writes is spelled.
 */
export function referenceTo(id: string, path?: string): string {
  return JSON.stringify(path ? { ref: id, path } : { ref: id });
}

/** A reference in arguments: `ref` with an optional `path`, or a whole result's `ref` with a `label`. */
type Reference = { ref: string; path?: string; label?: string };

function asReference(value: unknown): Reference | undefined {
  if (!meantAsReference(value)) return undefined;
  const { ref, path, label } = value as { ref: string; path?: unknown; label?: unknown };
  if (!Object.keys(value).every((key) => key === "ref" || key === "path" || key === "label"))
    return undefined;
  if (path !== undefined && (typeof path !== "string" || label !== undefined)) return undefined;
  if (label !== undefined && (typeof label !== "string" || !label.trim() || label.length > NAME_CHARS))
    return undefined;
  return path !== undefined ? { ref, path } : label !== undefined ? { ref, label } : { ref };
}

/** An object with a result id as its `ref`: a reference, or one written with more in it than ref and path. */
function meantAsReference(value: unknown): value is { ref: string; path?: unknown } {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const { ref } = value as { ref?: unknown };
  return typeof ref === "string" && ID.test(ref);
}

/** Why `value`, meant as a reference, is not one, and the reference to write instead. */
function misreference(value: { ref: string; path?: unknown; label?: unknown }): string {
  const extra = Object.keys(value).filter((key) => !["ref", "path", "label"].includes(key));
  const path = typeof value.path === "string" ? value.path : undefined;
  const instead = referenceTo(value.ref, path);
  if (extra.length) {
    return `${JSON.stringify(value)}: a reference holds ref and a path or a label, so ${extra.join(", ")} cannot go in it; write ${instead}, which brings the result's own data`;
  }
  if (path !== undefined && value.label !== undefined) {
    return `${JSON.stringify(value)}: a label names a whole result, not part of one; write ${instead}`;
  }
  return typeof value.path !== "string" && value.path !== undefined
    ? `${JSON.stringify(value)}: a reference's path is text, such as ${REFERENCE_EXAMPLES.column}; write ${referenceTo(value.ref)} for the whole result`
    : `${JSON.stringify(value)}: a label is a name of 1 to ${NAME_CHARS} characters, such as {"ref":"${value.ref}","label":"NVDA"}`;
}

/** References as the agents' instructions show them: a column, and one value of it. */
export const REFERENCE_EXAMPLES = {
  column: referenceTo("e7", "closes"),
  value: referenceTo("e7", "closes[-1]"),
};

type Resolved = { ok: true; value: unknown; inputs: string[] } | { ok: false; error: string };

const PART = /(?:^|\.)([A-Za-z_][A-Za-z0-9_]*)|\[(-?\d+)\]|\[((?:-?\d+)?):((?:-?\d+)?)\]/g;

/**
 * `args` with every reference replaced, for a call of run `at.run`'s step `at.step`. A result of that
 * same run and step is refused: the model had not seen it when it made the call.
 */
export function resolveReferences(
  args: unknown,
  source: ReferenceSource,
  at: { run: string; step: number },
): Resolved {
  const inputs = new Set<string>();
  const walk = (value: unknown): { value: unknown } | { error: string } => {
    const reference = asReference(value);
    if (reference) return lookUp(reference, source, at, inputs);
    if (meantAsReference(value)) return { error: misreference(value) };
    if (Array.isArray(value)) {
      const out: unknown[] = [];
      for (const item of value) {
        const resolved = walk(item);
        if ("error" in resolved) return resolved;
        out.push(resolved.value);
      }
      return { value: out };
    }
    if (value !== null && typeof value === "object") {
      const out: Record<string, unknown> = {};
      for (const [key, item] of Object.entries(value)) {
        const resolved = walk(item);
        if ("error" in resolved) return resolved;
        out[key] = resolved.value;
      }
      return { value: out };
    }
    return { value };
  };
  const resolved = walk(args);
  return "error" in resolved
    ? { ok: false, error: resolved.error }
    : { ok: true, value: resolved.value, inputs: [...inputs] };
}

/** Whether `args` hold a reference anywhere (or an object meant as one). */
export function holdsReference(args: unknown): boolean {
  if (meantAsReference(args)) return true;
  if (Array.isArray(args)) return args.some(holdsReference);
  if (args !== null && typeof args === "object") return Object.values(args).some(holdsReference);
  return false;
}

function lookUp(
  reference: Reference,
  source: ReferenceSource,
  at: { run: string; step: number },
  inputs: Set<string>,
): { value: unknown } | { error: string } {
  const fail = (why: string) => ({ error: `${JSON.stringify(reference)}: ${why}` });
  const id = reference.ref;
  // A path written with a leading dot (.closes) is read as without it.
  const path = (reference.path ?? "").replace(/^\./, "");
  if (!ID.test(id) || (path && !PATH.test(path))) {
    return fail(
      `a reference is {"ref": "eN"} with an optional path of fields, [N] indexes and [a:b] slices, such as ${REFERENCE_EXAMPLES.column}, ${REFERENCE_EXAMPLES.value} or ${referenceTo("e7", "closes[-20:]")}`,
    );
  }
  const found = source.payload(id);
  if ((!found && source.pending?.(id)) || (found && found.run === at.run && found.step === at.step)) {
    return fail(
      `${id} comes from a call in this same step, so it was not there yet when the calls were made. A result's id is given when the result comes back and cannot be known before: make this call in the next step, with the id the result came back with.`,
    );
  }
  if (!found) return fail(`there is no result ${id}`);
  if ("localOnly" in found) {
    return fail(
      `${id}'s data is not available here, only its preview (it was too large to keep with the session, or it stays on the computer that fetched it). Fetch it again to use it.`,
    );
  }
  let value: unknown = found.payload;
  let walked = "";
  const where = () => (walked ? `${walked} in ${id}` : id);
  for (const [, field, index, from, to] of path.matchAll(PART)) {
    if (from !== undefined && to !== undefined) {
      if (!Array.isArray(value)) return fail(`${where()} is not a list to slice`);
      const part = value.slice(from === "" ? undefined : Number(from), to === "" ? undefined : Number(to));
      if (!part.length)
        return fail(`the slice [${from}:${to}] of ${where()} (${value.length} values) is empty`);
      value = part;
      walked += `[${from}:${to}]`;
      continue;
    }
    if (field !== undefined) {
      if (Array.isArray(value))
        return fail(`${where()} is a list, not a record with fields; use an index such as [0]`);
      if (value === null || typeof value !== "object")
        return fail(`${where()} is a single value, with no fields`);
      if (!Object.hasOwn(value, field)) {
        return fail(`${where()} has no field ${field}; its fields are ${Object.keys(value).join(", ")}`);
      }
      value = (value as Record<string, unknown>)[field];
      walked += walked ? `.${field}` : field;
    } else {
      const n = Number(index);
      if (!Array.isArray(value)) return fail(`${where()} is not a list to index`);
      const position = n < 0 ? value.length + n : n;
      if (position < 0 || position >= value.length)
        return fail(`index ${n} is outside ${where()} (${value.length} values)`);
      value = value[position];
      walked += `[${n}]`;
    }
  }
  if (reference.label !== undefined) {
    if (value === null || typeof value !== "object" || Array.isArray(value))
      return fail(`${id} is not a record a label can name; write ${referenceTo(id)}`);
    value = { ...value, label: reference.label };
  }
  inputs.add(id);
  return { value };
}
