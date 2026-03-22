export function getActiveElement(el: HTMLElement): HTMLElement | null {
  let activeElement = el.ownerDocument.activeElement as HTMLElement | null

  while (activeElement?.shadowRoot) {
    const el = activeElement.shadowRoot.activeElement as HTMLElement | null
    if (el === activeElement) break
    else activeElement = el
  }

  return activeElement
}
