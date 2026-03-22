export as namespace Classcat

export interface ClassObject {
  [key: string]: boolean | any
}

export interface ClassArray extends Array<Class> {}

export type Class = string | number | null | undefined | ClassObject | ClassArray

/**
 * @param names A string, array or object of CSS class names (as keys).
 * @returns The class attribute string.
 */
export default function cc(names: Class): string
