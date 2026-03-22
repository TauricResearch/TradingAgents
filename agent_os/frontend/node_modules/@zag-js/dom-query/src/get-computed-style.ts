const styleCache = new WeakMap<HTMLElement, any>()

export function getComputedStyle(el: HTMLElement) {
  if (!styleCache.has(el)) {
    const win = el.ownerDocument.defaultView || window
    styleCache.set(el, win.getComputedStyle(el))
  }
  return styleCache.get(el)
}
