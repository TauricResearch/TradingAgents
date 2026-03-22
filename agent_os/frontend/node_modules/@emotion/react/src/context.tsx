import * as React from 'react'
import { useContext, forwardRef } from 'react'
import createCache, { EmotionCache } from '@emotion/cache'
import isDevelopment from '#is-development'
import isBrowser from '#is-browser'

let EmotionCacheContext =
  /* #__PURE__ */ React.createContext<EmotionCache | null>(
    // we're doing this to avoid preconstruct's dead code elimination in this one case
    // because this module is primarily intended for the browser and node
    // but it's also required in react native and similar environments sometimes
    // and we could have a special build just for that
    // but this is much easier and the native packages
    // might use a different theme context in the future anyway
    typeof HTMLElement !== 'undefined'
      ? /* #__PURE__ */ createCache({ key: 'css' })
      : null
  )

if (isDevelopment) {
  EmotionCacheContext.displayName = 'EmotionCacheContext'
}

export let CacheProvider = EmotionCacheContext.Provider

export let __unsafe_useEmotionCache = function useEmotionCache() {
  return useContext(EmotionCacheContext)
}

let withEmotionCache = function withEmotionCache<Props, RefType = any>(
  func: (
    props: React.PropsWithoutRef<Props>,
    context: EmotionCache,
    ref?: React.ForwardedRef<RefType>
  ) => React.ReactNode
):
  | React.FC<React.PropsWithoutRef<Props> & React.RefAttributes<RefType>>
  | React.ForwardRefExoticComponent<
      React.PropsWithoutRef<Props> & React.RefAttributes<RefType>
    > {
  return forwardRef<RefType, Props>((props, ref) => {
    // the cache will never be null in the browser
    let cache = useContext(EmotionCacheContext)!

    return func(props, cache, ref)
  })
}

if (!isBrowser) {
  withEmotionCache = function withEmotionCache(func) {
    return (props: Parameters<typeof func>[0]) => {
      let cache = useContext(EmotionCacheContext)
      if (cache === null) {
        // yes, we're potentially creating this on every render
        // it doesn't actually matter though since it's only on the server
        // so there will only every be a single render
        // that could change in the future because of suspense and etc. but for now,
        // this works and i don't want to optimise for a future thing that we aren't sure about
        cache = createCache({ key: 'css' })
        return (
          <EmotionCacheContext.Provider value={cache}>
            {func(props, cache)}
          </EmotionCacheContext.Provider>
        )
      } else {
        return func(props, cache)
      }
    }
  }
}

export { withEmotionCache }
