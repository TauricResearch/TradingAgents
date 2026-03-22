import { trackElementSize, type ElementSize } from "./track-size"

export interface TrackElementsSizeOptions<T extends HTMLElement | null> {
  getNodes: () => T[]
  observeMutation?: boolean
  callback: (size: ElementSize | undefined, index: number) => void
}

export function trackElementsSize<T extends HTMLElement | null>(options: TrackElementsSizeOptions<T>) {
  const { getNodes, observeMutation = true, callback } = options

  const cleanups: Array<VoidFunction | undefined> = []

  let firstNode: T | null = null

  function trigger() {
    const elements = getNodes()
    firstNode = elements[0]
    const fns = elements.map((element, index) =>
      trackElementSize(element, (size) => {
        callback(size, index)
      }),
    )
    cleanups.push(...fns)
  }

  trigger()

  if (observeMutation) {
    const fn = trackMutation(firstNode, trigger)
    cleanups.push(fn)
  }

  return () => {
    cleanups.forEach((cleanup) => {
      cleanup?.()
    })
  }
}

function trackMutation(el: HTMLElement | null, cb: () => void) {
  if (!el || !el.parentElement) return
  const win = el.ownerDocument?.defaultView ?? window
  const observer = new win.MutationObserver(() => {
    cb()
  })
  observer.observe(el.parentElement, { childList: true })
  return () => {
    observer.disconnect()
  }
}
