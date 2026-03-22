import * as React from 'react'
import isDevelopment from '#is-development'
import { withEmotionCache } from './context'
import { Theme, ThemeContext } from './theming'
import { insertStyles } from '@emotion/utils'
import { Options as SheetOptions, StyleSheet } from '@emotion/sheet'
import isBrowser from '#is-browser'
import { useInsertionEffectWithLayoutFallback } from '@emotion/use-insertion-effect-with-fallbacks'

import { Interpolation, serializeStyles } from '@emotion/serialize'

export interface GlobalProps {
  styles: Interpolation<Theme>
}

let warnedAboutCssPropForGlobal = false

// maintain place over rerenders.
// initial render from browser, insertBefore context.sheet.tags[0] or if a style hasn't been inserted there yet, appendChild
// initial client-side render from SSR, use place of hydrating tag

export let Global = /* #__PURE__ */ withEmotionCache<GlobalProps>(
  (props, cache) => {
    if (
      isDevelopment &&
      !warnedAboutCssPropForGlobal && // check for className as well since the user is
      // probably using the custom createElement which
      // means it will be turned into a className prop
      // I don't really want to add it to the type since it shouldn't be used
      (('className' in props && props.className) ||
        ('css' in props && props.css))
    ) {
      console.error(
        "It looks like you're using the css prop on Global, did you mean to use the styles prop instead?"
      )
      warnedAboutCssPropForGlobal = true
    }
    let styles = props.styles

    let serialized = serializeStyles(
      [styles],
      undefined,
      React.useContext(ThemeContext)
    )

    if (!isBrowser) {
      let serializedNames = serialized.name
      let serializedStyles = serialized.styles
      let next = serialized.next
      while (next !== undefined) {
        serializedNames += ' ' + next.name
        serializedStyles += next.styles
        next = next.next
      }

      let shouldCache = cache.compat === true

      let rules = cache.insert(
        ``,
        { name: serializedNames, styles: serializedStyles },
        cache.sheet,
        shouldCache
      )

      if (shouldCache) {
        return null
      }

      return (
        <style
          {...{
            [`data-emotion`]: `${cache.key}-global ${serializedNames}`,
            dangerouslySetInnerHTML: { __html: rules! },
            nonce: cache.sheet.nonce
          }}
        />
      )
    }

    // yes, i know these hooks are used conditionally
    // but it is based on a constant that will never change at runtime
    // it's effectively like having two implementations and switching them out
    // so it's not actually breaking anything

    let sheetRef = React.useRef<
      [sheet: StyleSheet, isRehydrating: boolean] | undefined
    >()

    useInsertionEffectWithLayoutFallback(() => {
      const key = `${cache.key}-global`

      // use case of https://github.com/emotion-js/emotion/issues/2675
      let sheet = new (cache.sheet.constructor as {
        new (options: SheetOptions): StyleSheet
      })({
        key,
        nonce: cache.sheet.nonce,
        container: cache.sheet.container,
        speedy: cache.sheet.isSpeedy
      })
      let rehydrating = false
      let node: HTMLStyleElement | null = document.querySelector(
        `style[data-emotion="${key} ${serialized.name}"]`
      )
      if (cache.sheet.tags.length) {
        sheet.before = cache.sheet.tags[0]
      }
      if (node !== null) {
        rehydrating = true
        // clear the hash so this node won't be recognizable as rehydratable by other <Global/>s
        node.setAttribute('data-emotion', key)
        sheet.hydrate([node])
      }
      sheetRef.current = [sheet, rehydrating]
      return () => {
        sheet.flush()
      }
    }, [cache])

    useInsertionEffectWithLayoutFallback(() => {
      let sheetRefCurrent = sheetRef.current!
      let [sheet, rehydrating] = sheetRefCurrent
      if (rehydrating) {
        sheetRefCurrent[1] = false
        return
      }
      if (serialized.next !== undefined) {
        // insert keyframes
        insertStyles(cache, serialized.next, true)
      }

      if (sheet.tags.length) {
        // if this doesn't exist then it will be null so the style element will be appended
        let element = sheet.tags[sheet.tags.length - 1].nextElementSibling
        sheet.before = element
        sheet.flush()
      }
      cache.insert(``, serialized, sheet, false)
    }, [cache, serialized.name])

    return null
  }
)

if (isDevelopment) {
  Global.displayName = 'EmotionGlobal'
}
