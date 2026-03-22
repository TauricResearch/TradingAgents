type Root = Document | Element | null | undefined

export function queryAll<T extends HTMLElement = HTMLElement>(root: Root, selector: string) {
  return Array.from(root?.querySelectorAll<T>(selector) ?? [])
}

export function query<T extends HTMLElement = HTMLElement>(root: Root, selector: string) {
  return root?.querySelector<T>(selector)
}
