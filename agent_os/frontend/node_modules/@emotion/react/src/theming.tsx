import * as React from 'react'
import weakMemoize from '@emotion/weak-memoize'
import isDevelopment from '#is-development'
import hoistNonReactStatics from './_isolated-hnrs'
import { DistributiveOmit, PropsOf } from './types'

// tslint:disable-next-line: no-empty-interface
export interface Theme {}

export interface ThemeProviderProps {
  theme: Partial<Theme> | ((outerTheme: Theme) => Theme)
  children: React.ReactNode
}

export interface ThemeProvider {
  (props: ThemeProviderProps): React.ReactElement
}

export type WithTheme<P, T> = P extends { theme: infer Theme }
  ? P & { theme: Exclude<Theme, undefined> }
  : P & { theme: T }

export const ThemeContext = /* #__PURE__ */ React.createContext({} as Theme)
if (isDevelopment) {
  ThemeContext.displayName = 'EmotionThemeContext'
}

export const useTheme = () => React.useContext(ThemeContext)

const getTheme = (
  outerTheme: Theme,
  theme: Partial<Theme> | ((theme: Theme) => Theme)
): Theme => {
  if (typeof theme === 'function') {
    const mergedTheme = theme(outerTheme)
    if (
      isDevelopment &&
      (mergedTheme == null ||
        typeof mergedTheme !== 'object' ||
        Array.isArray(mergedTheme))
    ) {
      throw new Error(
        '[ThemeProvider] Please return an object from your theme function, i.e. theme={() => ({})}!'
      )
    }
    return mergedTheme
  }
  if (
    isDevelopment &&
    (theme == null || typeof theme !== 'object' || Array.isArray(theme))
  ) {
    throw new Error(
      '[ThemeProvider] Please make your theme prop a plain object'
    )
  }

  return { ...outerTheme, ...theme }
}

let createCacheWithTheme = /* #__PURE__ */ weakMemoize((outerTheme: Theme) => {
  return weakMemoize((theme: Partial<Theme> | ((theme: Theme) => Theme)) => {
    return getTheme(outerTheme, theme)
  })
})

export interface ThemeProviderProps {
  theme: Partial<Theme> | ((outerTheme: Theme) => Theme)
  children: React.ReactNode
}

export const ThemeProvider = (props: ThemeProviderProps) => {
  let theme = React.useContext(ThemeContext)

  if (props.theme !== theme) {
    theme = createCacheWithTheme(theme)(props.theme)
  }
  return (
    <ThemeContext.Provider value={theme}>
      {props.children}
    </ThemeContext.Provider>
  )
}

export function withTheme<
  C extends React.ComponentType<React.ComponentProps<C>>
>(
  Component: C
): React.ForwardRefExoticComponent<
  DistributiveOmit<PropsOf<C>, 'theme'> & { theme?: Theme }
>
export function withTheme(
  Component: React.ComponentType<any>
): React.ForwardRefExoticComponent<any> {
  const componentName = Component.displayName || Component.name || 'Component'

  let WithTheme = React.forwardRef(function render(props, ref) {
    let theme = React.useContext(ThemeContext)

    return <Component theme={theme} ref={ref} {...props} />
  })

  WithTheme.displayName = `WithTheme(${componentName})`

  return hoistNonReactStatics(WithTheme, Component)
}
