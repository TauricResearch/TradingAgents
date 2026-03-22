const isNode = (el: any): el is Node => el.nodeType !== undefined

export const isShadowRoot = (el: any): el is ShadowRoot =>
  el && isNode(el) && el.nodeType === Node.DOCUMENT_FRAGMENT_NODE && "host" in el
