System.register(['react', 'use-sync-external-store/shim/with-selector', 'zustand/vanilla'], (function (exports) {
  'use strict';
  var ReactExports, useSyncExternalStoreExports, createStore;
  return {
    setters: [function (module) {
      ReactExports = module.default;
    }, function (module) {
      useSyncExternalStoreExports = module.default;
    }, function (module) {
      createStore = module.createStore;
    }],
    execute: (function () {

      exports("useStoreWithEqualityFn", useStoreWithEqualityFn);

      const { useDebugValue } = ReactExports;
      const { useSyncExternalStoreWithSelector } = useSyncExternalStoreExports;
      const identity = (arg) => arg;
      function useStoreWithEqualityFn(api, selector = identity, equalityFn) {
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
      const createWithEqualityFnImpl = (createState, defaultEqualityFn) => {
        const api = createStore(createState);
        const useBoundStoreWithEqualityFn = (selector, equalityFn = defaultEqualityFn) => useStoreWithEqualityFn(api, selector, equalityFn);
        Object.assign(useBoundStoreWithEqualityFn, api);
        return useBoundStoreWithEqualityFn;
      };
      const createWithEqualityFn = exports("createWithEqualityFn", (createState, defaultEqualityFn) => createState ? createWithEqualityFnImpl(createState, defaultEqualityFn) : createWithEqualityFnImpl);

    })
  };
}));
