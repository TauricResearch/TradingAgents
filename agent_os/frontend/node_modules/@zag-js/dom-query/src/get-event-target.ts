export function getEventTarget<T extends EventTarget>(event: Event): T | null {
  return (event.composedPath?.()[0] ?? event.target) as T | null
}
