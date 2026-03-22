import isDevelopment from '#is-development'
import pkg from '../package.json'
export type { EmotionCache } from '@emotion/cache'
export type {
  ArrayInterpolation,
  ComponentSelector,
  CSSObject,
  FunctionInterpolation,
  Interpolation,
  Keyframes,
  SerializedStyles
} from '@emotion/serialize'
export {
  withEmotionCache,
  CacheProvider,
  __unsafe_useEmotionCache
} from './context'
export { jsx } from './jsx'
export { jsx as createElement } from './jsx'
export { Global } from './global'
export type { GlobalProps } from './global'
export { keyframes } from './keyframes'
export { ClassNames } from './class-names'
export type {
  ClassNamesArg,
  ClassNamesContent,
  ClassNamesProps,
  ArrayClassNamesArg
} from './class-names'
export { ThemeContext, useTheme, ThemeProvider, withTheme } from './theming'
export type { Theme, ThemeProviderProps, WithTheme } from './theming'
export { default as css } from './css'
export type { DistributiveOmit, PropsOf } from './types'

declare const global: Record<string, unknown>
declare const jest: unknown
declare const vi: unknown

if (isDevelopment) {
  const isBrowser = typeof document !== 'undefined'
  // #1727, #2905 for some reason Jest and Vitest evaluate modules twice if some consuming module gets mocked
  const isTestEnv = typeof jest !== 'undefined' || typeof vi !== 'undefined'

  if (isBrowser && !isTestEnv) {
    // globalThis has wide browser support - https://caniuse.com/?search=globalThis, Node.js 12 and later
    const globalContext: Record<string, unknown> =
      typeof globalThis !== 'undefined'
        ? globalThis // eslint-disable-line no-undef
        : isBrowser
          ? window
          : global
    const globalKey = `__EMOTION_REACT_${pkg.version.split('.')[0]}__`
    if (globalContext[globalKey]) {
      console.warn(
        'You are loading @emotion/react when it is already loaded. Running ' +
          'multiple instances may cause problems. This can happen if multiple ' +
          'versions are used, or if multiple builds of the same version are ' +
          'used.'
      )
    }
    globalContext[globalKey] = true
  }
}
