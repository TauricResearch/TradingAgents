import * as React from 'react'
import isBrowser from '#is-browser'

const syncFallback = <T>(create: () => T) => create()

const useInsertionEffect = React[
  ('useInsertion' + 'Effect') as 'useInsertionEffect'
]
  ? (React[('useInsertion' + 'Effect') as 'useInsertionEffect'] as <T>(
      create: () => T
    ) => T | undefined)
  : false

export const useInsertionEffectAlwaysWithSyncFallback: <T>(
  create: () => T
) => T | undefined = !isBrowser
  ? syncFallback
  : useInsertionEffect || syncFallback

export const useInsertionEffectWithLayoutFallback: typeof React.useLayoutEffect =
  useInsertionEffect || React.useLayoutEffect
