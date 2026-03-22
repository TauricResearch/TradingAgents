export function nextTick(fn: VoidFunction) {
  const set = new Set<VoidFunction>()
  function raf(fn: VoidFunction) {
    const id = globalThis.requestAnimationFrame(fn)
    set.add(() => globalThis.cancelAnimationFrame(id))
  }
  raf(() => raf(fn))
  return function cleanup() {
    set.forEach((fn) => fn())
  }
}

export function raf(fn: VoidFunction) {
  const id = globalThis.requestAnimationFrame(fn)
  return () => {
    globalThis.cancelAnimationFrame(id)
  }
}
