import { isDocument } from "./is-document"
import { isHTMLElement } from "./is-html-element"
import { isShadowRoot } from "./is-shadow-root"

export function getDocument(el: Element | Node | Document | null) {
  if (isDocument(el)) return el
  return el?.ownerDocument ?? document
}

export function getWindow(el: Node | ShadowRoot | Document | undefined) {
  if (isShadowRoot(el)) return getWindow(el.host)
  if (isDocument(el)) return el.defaultView ?? window
  if (isHTMLElement(el)) return el.ownerDocument?.defaultView ?? window
  return window
}
