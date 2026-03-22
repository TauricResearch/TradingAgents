export interface ElementSize {
  width: number
  height: number
}

export type ElementSizeCallback = (size: ElementSize | undefined) => void

export function trackElementSize(element: HTMLElement | null, callback: ElementSizeCallback) {
  if (!element) {
    callback(undefined)
    return
  }

  callback({ width: element.offsetWidth, height: element.offsetHeight })

  const win = element.ownerDocument.defaultView ?? window

  const observer = new win.ResizeObserver((entries) => {
    if (!Array.isArray(entries) || !entries.length) return

    const [entry] = entries
    let width: number
    let height: number

    if ("borderBoxSize" in entry) {
      const borderSizeEntry = entry["borderBoxSize"]
      const borderSize = Array.isArray(borderSizeEntry) ? borderSizeEntry[0] : borderSizeEntry
      width = borderSize["inlineSize"]
      height = borderSize["blockSize"]
    } else {
      width = element.offsetWidth
      height = element.offsetHeight
    }

    callback({ width, height })
  })

  observer.observe(element, { box: "border-box" })

  return () => observer.unobserve(element)
}
