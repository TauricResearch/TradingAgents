import * as React from 'react'
import { withEmotionCache } from './context'
import { Theme, ThemeContext } from './theming'
import {
  EmotionCache,
  getRegisteredStyles,
  insertStyles,
  registerStyles,
  SerializedStyles
} from '@emotion/utils'
import { hasOwn } from './utils'
import { Interpolation, serializeStyles } from '@emotion/serialize'
import isDevelopment from '#is-development'
import isBrowser from '#is-browser'
import { getLabelFromStackTrace } from './get-label-from-stack-trace'
import { useInsertionEffectAlwaysWithSyncFallback } from '@emotion/use-insertion-effect-with-fallbacks'

const typePropName = '__EMOTION_TYPE_PLEASE_DO_NOT_USE__'

const labelPropName = '__EMOTION_LABEL_PLEASE_DO_NOT_USE__'

interface EmotionProps {
  css: Interpolation<Theme>
  [typePropName]: React.ElementType
  [labelPropName]?: string
  [key: string]: unknown
}

export const createEmotionProps = (
  type: React.ElementType,
  props: { css: Interpolation<Theme> }
): EmotionProps => {
  if (
    isDevelopment &&
    typeof props.css === 'string' &&
    // check if there is a css declaration
    props.css.indexOf(':') !== -1
  ) {
    throw new Error(
      `Strings are not allowed as css prop values, please wrap it in a css template literal from '@emotion/react' like this: css\`${props.css}\``
    )
  }

  let newProps = {} as EmotionProps

  for (let key in props) {
    if (hasOwn.call(props, key)) {
      newProps[key] = props[key as keyof typeof props]
    }
  }

  newProps[typePropName] = type

  // Runtime labeling is an opt-in feature because:
  // - It causes hydration warnings when using Safari and SSR
  // - It can degrade performance if there are a huge number of elements
  //
  // Even if the flag is set, we still don't compute the label if it has already
  // been determined by the Babel plugin.
  if (
    isDevelopment &&
    typeof globalThis !== 'undefined' &&
    !!(globalThis as any).EMOTION_RUNTIME_AUTO_LABEL &&
    !!props.css &&
    (typeof props.css !== 'object' ||
      !('name' in props.css) ||
      typeof props.css.name !== 'string' ||
      props.css.name.indexOf('-') === -1)
  ) {
    const label = getLabelFromStackTrace(new Error().stack)
    if (label) newProps[labelPropName] = label
  }

  return newProps
}

const Insertion = ({
  cache,
  serialized,
  isStringTag
}: {
  cache: EmotionCache
  serialized: SerializedStyles
  isStringTag: boolean
}) => {
  registerStyles(cache, serialized, isStringTag)

  const rules = useInsertionEffectAlwaysWithSyncFallback(() =>
    insertStyles(cache, serialized, isStringTag)
  )

  if (!isBrowser && rules !== undefined) {
    let serializedNames = serialized.name
    let next = serialized.next
    while (next !== undefined) {
      serializedNames += ' ' + next.name
      next = next.next
    }
    return (
      <style
        {...{
          [`data-emotion`]: `${cache.key} ${serializedNames}`,
          dangerouslySetInnerHTML: { __html: rules },
          nonce: cache.sheet.nonce
        }}
      />
    )
  }
  return null
}

let Emotion = /* #__PURE__ */ withEmotionCache<EmotionProps>(
  (props, cache, ref) => {
    let cssProp = props.css as EmotionProps['css']

    // so that using `css` from `emotion` and passing the result to the css prop works
    // not passing the registered cache to serializeStyles because it would
    // make certain babel optimisations not possible
    if (
      typeof cssProp === 'string' &&
      cache.registered[cssProp] !== undefined
    ) {
      cssProp = cache.registered[cssProp]
    }

    let WrappedComponent = props[
      typePropName
    ] as EmotionProps[typeof typePropName]
    let registeredStyles = [cssProp]
    let className = ''

    if (typeof props.className === 'string') {
      className = getRegisteredStyles(
        cache.registered,
        registeredStyles,
        props.className
      )
    } else if (props.className != null) {
      className = `${props.className} `
    }

    let serialized = serializeStyles(
      registeredStyles,
      undefined,
      React.useContext(ThemeContext)
    )

    if (isDevelopment && serialized.name.indexOf('-') === -1) {
      let labelFromStack = props[labelPropName]
      if (labelFromStack) {
        serialized = serializeStyles([
          serialized,
          'label:' + labelFromStack + ';'
        ])
      }
    }

    className += `${cache.key}-${serialized.name}`

    const newProps: Record<string, unknown> = {}
    for (let key in props) {
      if (
        hasOwn.call(props, key) &&
        key !== 'css' &&
        key !== typePropName &&
        (!isDevelopment || key !== labelPropName)
      ) {
        newProps[key] = props[key]
      }
    }
    newProps.className = className
    if (ref) {
      newProps.ref = ref
    }

    return (
      <>
        <Insertion
          cache={cache}
          serialized={serialized}
          isStringTag={typeof WrappedComponent === 'string'}
        />
        <WrappedComponent {...newProps} />
      </>
    )
  }
)

if (isDevelopment) {
  Emotion.displayName = 'EmotionCssPropInternal'
}

export default Emotion
