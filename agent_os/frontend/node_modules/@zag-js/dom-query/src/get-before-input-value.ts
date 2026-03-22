export function getBeforeInputValue(event: Pick<InputEvent, "currentTarget">) {
  const { selectionStart, selectionEnd, value } = event.currentTarget as HTMLInputElement
  return value.slice(0, selectionStart!) + (event as any).data + value.slice(selectionEnd!)
}
