import { isHTMLElement } from "./is-html-element"

type Target = HTMLElement | EventTarget | null | undefined

export function contains(parent: Target, child: Target) {
  if (!parent || !child) return false
  if (!isHTMLElement(parent) || !isHTMLElement(child)) return false
  return parent === child || parent.contains(child)
}

export const isSelfEvent = (event: Pick<UIEvent, "currentTarget" | "target">) =>
  contains(event.currentTarget, event.target)
