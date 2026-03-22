System.register(['zustand/vanilla', 'react', 'use-sync-external-store/shim/with-selector'], (function (exports) {
  'use strict';
  var _starExcludes = {
    __proto__: null,
    create: 1,
    default: 1,
    useStore: 1
  };
  var createStore, ReactExports, useSyncExternalStoreExports;
  return {
    setters: [function (module) {
      createStore = module.createStore;
      var setter = { __proto__: null };
      for (var name in module) {
        if (!_starExcludes[name]) setter[name] = module[name];
      }
      exports(setter);
    }, function (module) {
      ReactExports = module.default;
    }, function (module) {
      useSyncExternalStoreExports = module.default;
    }],
    execute: (function () {

      exports("useStore", useStore);

      const { useDebugValue } = ReactExports;
      const { useSyncExternalStoreWithSelector } = useSyncExternalStoreExports;
      let didWarnAboutEqualityFn = false;
      const identity = (arg) => arg;
      function useStore(api, selector = identity, equalityFn) {
        if (equalityFn && !didWarnAboutEqualityFn) {
          console.warn(
            "[DEPRECATED] Use `createWithEqualityFn` instead of `create` or use `useStoreWithEqualityFn` instead of `useStore`. They can be imported from 'zustand/traditional'. https://github.com/pmndrs/zustand/discussions/1937"
          );
          didWarnAboutEqualityFn = true;
        }
        const slice = useSyncExternalStoreWithSelector(
          api.subscribe,
          api.getState,
          api.getServerState || api.getInitialState,
          selector,
          equalityFn
        );
        useDebugValue(slice);
        return slice;
      }
      const createImpl = (createState) => {
        if (typeof createState !== "function") {
          console.warn(
            "[DEPRECATED] Passing a vanilla store will be unsupported in a future version. Instead use `import { useStore } from 'zustand'`."
          );
        }
        const api = typeof createState === "function" ? createStore(createState) : createState;
        const useBoundStore = (selector, equalityFn) => useStore(api, selector, equalityFn);
        Object.assign(useBoundStore, api);
        return useBoundStore;
      };
      const create = exports("create", (createState) => createState ? createImpl(createState) : createImpl);
      var react = exports("default", (createState) => {
        {
          console.warn(
            "[DEPRECATED] Default export is deprecated. Instead use `import { create } from 'zustand'`."
          );
        }
        return create(createState);
      });

    })
  };
}));
