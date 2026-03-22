import { getByText } from "./get-by-text"

export interface TypeaheadState {
  keysSoFar: string
  timer: number
}

export interface TypeaheadOptions {
  state: TypeaheadState
  activeId: string | null
  key: string
  timeout?: number
}

function getByTypeaheadImpl<T extends HTMLElement>(_items: T[], options: TypeaheadOptions) {
  const { state, activeId, key, timeout = 350 } = options

  const search = state.keysSoFar + key
  const isRepeated = search.length > 1 && Array.from(search).every((char) => char === search[0])

  const query = isRepeated ? search[0] : search

  let items = _items.slice()

  const next = getByText(items, query, activeId)

  function cleanup() {
    clearTimeout(state.timer)
    state.timer = -1
  }

  function update(value: string) {
    state.keysSoFar = value
    cleanup()

    if (value !== "") {
      state.timer = +setTimeout(() => {
        update("")
        cleanup()
      }, timeout)
    }
  }

  update(search)

  return next
}
export const getByTypeahead = /*#__PURE__*/ Object.assign(getByTypeaheadImpl, {
  defaultOptions: { keysSoFar: "", timer: -1 },
  isValidEvent: isValidTypeaheadEvent,
})

function isValidTypeaheadEvent(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey">) {
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey
}
