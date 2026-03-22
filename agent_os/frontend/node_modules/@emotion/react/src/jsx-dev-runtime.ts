import * as ReactJSXRuntimeDev from 'react/jsx-dev-runtime'
import Emotion, { createEmotionProps } from './emotion-element'
import { hasOwn } from './utils'
import { Interpolation } from '@emotion/serialize'
import { Theme } from './theming'
export type { EmotionJSX as JSX } from './jsx-namespace'

export const Fragment = ReactJSXRuntimeDev.Fragment

export const jsxDEV: typeof ReactJSXRuntimeDev.jsxDEV = (
  type,
  props,
  key,
  isStaticChildren,
  source,
  self
) => {
  if (!hasOwn.call(props, 'css')) {
    return ReactJSXRuntimeDev.jsxDEV(
      type,
      props,
      key,
      isStaticChildren,
      source,
      self
    )
  }

  return ReactJSXRuntimeDev.jsxDEV(
    Emotion,
    createEmotionProps(type, props as { css: Interpolation<Theme> }),
    key,
    isStaticChildren,
    source,
    self
  )
}
