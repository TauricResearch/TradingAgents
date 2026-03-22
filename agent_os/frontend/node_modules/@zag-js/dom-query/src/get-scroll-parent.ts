import { isHTMLElement } from "./is-html-element"

function isScrollParent(el: HTMLElement): boolean {
  const win = el.ownerDocument.defaultView || window
  const { overflow, overflowX, overflowY } = win.getComputedStyle(el)
  return /auto|scroll|overlay|hidden/.test(overflow + overflowY + overflowX)
}

export function getParent(el: HTMLElement): HTMLElement {
  if (el.localName === "html") return el
  return el.assignedSlot || el.parentElement || el.ownerDocument.documentElement
}

export function getScrollParent(el: HTMLElement): HTMLElement {
  if (["html", "body", "#document"].includes(el.localName)) {
    return el.ownerDocument.body
  }

  if (isHTMLElement(el) && isScrollParent(el)) {
    return el
  }

  return getScrollParent(getParent(el))
}

type Target = Array<VisualViewport | Window | HTMLElement | null>

export function getScrollParents(el: HTMLElement, list: Target = []): Target {
  const parent = getScrollParent(el)
  const isBody = parent === el.ownerDocument.body
  const win = parent.ownerDocument.defaultView || window

  //@ts-expect-error
  const target = isBody ? [win].concat(win.visualViewport || [], isScrollParent(parent) ? parent : []) : parent

  const parents = list.concat(target)
  return isBody ? parents : parents.concat(getScrollParents(getParent(<HTMLElement>target)))
}
