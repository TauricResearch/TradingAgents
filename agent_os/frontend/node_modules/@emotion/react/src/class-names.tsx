import * as React from 'react'
import {
  EmotionCache,
  getRegisteredStyles,
  insertStyles,
  registerStyles,
  SerializedStyles
} from '@emotion/utils'
import { CSSInterpolation, serializeStyles } from '@emotion/serialize'
import isDevelopment from '#is-development'
import { withEmotionCache } from './context'
import { Theme, ThemeContext } from './theming'
import { useInsertionEffectAlwaysWithSyncFallback } from '@emotion/use-insertion-effect-with-fallbacks'
import isBrowser from '#is-browser'

export interface ArrayClassNamesArg extends Array<ClassNamesArg> {}

export type ClassNamesArg =
  | undefined
  | null
  | string
  | boolean
  | { [className: string]: boolean | null | undefined }
  | ArrayClassNamesArg

let classnames = (args: ArrayClassNamesArg): string => {
  let len = args.length
  let i = 0
  let cls = ''
  for (; i < len; i++) {
    let arg = args[i]
    if (arg == null) continue

    let toAdd
    switch (typeof arg) {
      case 'boolean':
        break
      case 'object': {
        if (Array.isArray(arg)) {
          toAdd = classnames(arg)
        } else {
          if (
            isDevelopment &&
            arg.styles !== undefined &&
            arg.name !== undefined
          ) {
            console.error(
              'You have passed styles created with `css` from `@emotion/react` package to the `cx`.\n' +
                '`cx` is meant to compose class names (strings) so you should convert those styles to a class name by passing them to the `css` received from <ClassNames/> component.'
            )
          }
          toAdd = ''
          for (const k in arg) {
            if (arg[k] && k) {
              toAdd && (toAdd += ' ')
              toAdd += k
            }
          }
        }
        break
      }
      default: {
        toAdd = arg
      }
    }
    if (toAdd) {
      cls && (cls += ' ')
      cls += toAdd
    }
  }
  return cls
}
function merge(
  registered: EmotionCache['registered'],
  css: ClassNamesContent['css'],
  className: string
) {
  const registeredStyles: string[] = []

  const rawClassName = getRegisteredStyles(
    registered,
    registeredStyles,
    className
  )

  if (registeredStyles.length < 2) {
    return className
  }
  return rawClassName + css(registeredStyles)
}

const Insertion = ({
  cache,
  serializedArr
}: {
  cache: EmotionCache
  serializedArr: SerializedStyles[]
}) => {
  let rules = useInsertionEffectAlwaysWithSyncFallback(() => {
    let rules = ''
    for (let i = 0; i < serializedArr.length; i++) {
      let res = insertStyles(cache, serializedArr[i], false)
      if (!isBrowser && res !== undefined) {
        rules += res
      }
    }
    if (!isBrowser) {
      return rules
    }
  })

  if (!isBrowser && rules!.length !== 0) {
    return (
      <style
        {...{
          [`data-emotion`]: `${cache.key} ${serializedArr
            .map(serialized => serialized.name)
            .join(' ')}`,
          dangerouslySetInnerHTML: { __html: rules! },
          nonce: cache.sheet.nonce
        }}
      />
    )
  }
  return null
}

export interface ClassNamesContent {
  css(template: TemplateStringsArray, ...args: Array<CSSInterpolation>): string
  css(...args: Array<CSSInterpolation>): string
  cx(...args: Array<ClassNamesArg>): string
  theme: Theme
}

export interface ClassNamesProps {
  children(content: ClassNamesContent): React.ReactNode
}

export const ClassNames = /* #__PURE__ */ withEmotionCache<ClassNamesProps>(
  (props, cache) => {
    let hasRendered = false
    let serializedArr: SerializedStyles[] = []

    let css: ClassNamesContent['css'] = (...args) => {
      if (hasRendered && isDevelopment) {
        throw new Error('css can only be used during render')
      }

      let serialized = serializeStyles(args, cache.registered)
      serializedArr.push(serialized)
      // registration has to happen here as the result of this might get consumed by `cx`
      registerStyles(cache, serialized, false)
      return `${cache.key}-${serialized.name}`
    }
    let cx = (...args: Array<ClassNamesArg>) => {
      if (hasRendered && isDevelopment) {
        throw new Error('cx can only be used during render')
      }
      return merge(cache.registered, css, classnames(args))
    }
    let content = {
      css,
      cx,
      theme: React.useContext(ThemeContext)
    }
    let ele = props.children(content)
    hasRendered = true

    return (
      <>
        <Insertion cache={cache} serializedArr={serializedArr} />
        {ele}
      </>
    )
  }
)

if (isDevelopment) {
  ClassNames.displayName = 'EmotionClassNames'
}
