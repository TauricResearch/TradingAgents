import * as ReactJSXRuntime from 'react/jsx-runtime'
import Emotion, { createEmotionProps } from './emotion-element'
import { hasOwn } from './utils'
import { Interpolation } from '@emotion/serialize'
import { Theme } from './theming'
export type { EmotionJSX as JSX } from './jsx-namespace'

export const Fragment = ReactJSXRuntime.Fragment

export const jsx: typeof ReactJSXRuntime.jsx = (type, props, key) => {
  if (!hasOwn.call(props, 'css')) {
    return ReactJSXRuntime.jsx(type, props, key)
  }

  return ReactJSXRuntime.jsx(
    Emotion,
    createEmotionProps(type, props as { css: Interpolation<Theme> }),
    key
  )
}

export const jsxs: typeof ReactJSXRuntime.jsxs = (type, props, key) => {
  if (!hasOwn.call(props, 'css')) {
    return ReactJSXRuntime.jsxs(type, props, key)
  }

  return ReactJSXRuntime.jsxs(
    Emotion,
    createEmotionProps(type, props as { css: Interpolation<Theme> }),
    key
  )
}
