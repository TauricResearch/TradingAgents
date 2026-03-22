import { isHTMLElement } from "./is-html-element"

export function isEditableElement(el: HTMLElement | EventTarget | null) {
  if (el == null || !isHTMLElement(el)) {
    return false
  }

  try {
    const win = el.ownerDocument.defaultView || window
    return (
      (el instanceof win.HTMLInputElement && el.selectionStart != null) ||
      /(textarea|select)/.test(el.localName) ||
      el.isContentEditable
    )
  } catch {
    return false
  }
}
