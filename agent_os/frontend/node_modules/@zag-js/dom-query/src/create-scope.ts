type Ctx = { getRootNode?: () => Document | ShadowRoot | Node }

const getDocument = (node: Document | ShadowRoot | Node) => {
  if (node.nodeType === Node.DOCUMENT_NODE) return node as Document
  return node.ownerDocument ?? document
}

export function createScope<T>(methods: T) {
  const screen = {
    getRootNode: (ctx: Ctx) => (ctx.getRootNode?.() ?? document) as Document | ShadowRoot,
    getDoc: (ctx: Ctx) => getDocument(screen.getRootNode(ctx)),
    getWin: (ctx: Ctx) => screen.getDoc(ctx).defaultView ?? window,
    getActiveElement: (ctx: Ctx) => screen.getDoc(ctx).activeElement as HTMLElement | null,
    isActiveElement: (ctx: Ctx, elem: HTMLElement | null) => elem === screen.getActiveElement(ctx),
    focus(ctx: Ctx, elem: HTMLElement | null | undefined) {
      if (elem == null) return
      if (!screen.isActiveElement(ctx, elem)) elem.focus({ preventScroll: true })
    },
    getById: <T extends HTMLElement = HTMLElement>(ctx: Ctx, id: string) =>
      screen.getRootNode(ctx).getElementById(id) as T | null,
    setValue: <T extends { value: string }>(elem: T | null, value: string | number | null | undefined) => {
      if (elem == null || value == null) return
      const valueAsString = value.toString()
      if (elem.value === valueAsString) return
      elem.value = value.toString()
    },
  }
  return { ...screen, ...methods }
}
