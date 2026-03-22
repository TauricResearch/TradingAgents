import isBrowser from '#is-browser'
import { RegisteredCache, EmotionCache, SerializedStyles } from './types'

export function getRegisteredStyles(
  registered: RegisteredCache,
  registeredStyles: string[],
  classNames: string
): string {
  let rawClassName = ''

  classNames.split(' ').forEach(className => {
    if (registered[className] !== undefined) {
      registeredStyles.push(`${registered[className]};`)
    } else if (className) {
      rawClassName += `${className} `
    }
  })
  return rawClassName
}

export const registerStyles = (
  cache: EmotionCache,
  serialized: SerializedStyles,
  isStringTag: boolean
): void => {
  let className = `${cache.key}-${serialized.name}`
  if (
    // we only need to add the styles to the registered cache if the
    // class name could be used further down
    // the tree but if it's a string tag, we know it won't
    // so we don't have to add it to registered cache.
    // this improves memory usage since we can avoid storing the whole style string
    (isStringTag === false ||
      // we need to always store it if we're in compat mode and
      // in node since emotion-server relies on whether a style is in
      // the registered cache to know whether a style is global or not
      // also, note that this check will be dead code eliminated in the browser
      (isBrowser === false && cache.compat !== undefined)) &&
    cache.registered[className] === undefined
  ) {
    cache.registered[className] = serialized.styles
  }
}

export const insertStyles = (
  cache: EmotionCache,
  serialized: SerializedStyles,
  isStringTag: boolean
) => {
  registerStyles(cache, serialized, isStringTag)

  let className = `${cache.key}-${serialized.name}`

  if (cache.inserted[serialized.name] === undefined) {
    let stylesForSSR = ''
    let current: SerializedStyles | undefined = serialized
    do {
      let maybeStyles = cache.insert(
        serialized === current ? `.${className}` : '',
        current,
        cache.sheet,
        true
      )
      if (!isBrowser && maybeStyles !== undefined) {
        stylesForSSR += maybeStyles
      }
      current = current.next
    } while (current !== undefined)
    if (!isBrowser && stylesForSSR.length !== 0) {
      return stylesForSSR
    }
  }
}

export * from './types'
