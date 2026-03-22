(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports, require('react'), require('use-sync-external-store/shim/with-selector'), require('zustand/vanilla')) :
  typeof define === 'function' && define.amd ? define(['exports', 'react', 'use-sync-external-store/shim/with-selector', 'zustand/vanilla'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.zustandTraditional = {}, global.React, global.useSyncExternalStoreShimWithSelector, global.zustandVanilla));
})(this, (function (exports, ReactExports, useSyncExternalStoreExports, vanilla) { 'use strict';

  var useDebugValue = ReactExports.useDebugValue;
  var useSyncExternalStoreWithSelector = useSyncExternalStoreExports.useSyncExternalStoreWithSelector;
  var identity = function identity(arg) {
    return arg;
  };
  function useStoreWithEqualityFn(api, selector, equalityFn) {
    if (selector === void 0) {
      selector = identity;
    }
    var slice = useSyncExternalStoreWithSelector(api.subscribe, api.getState, api.getServerState || api.getInitialState, selector, equalityFn);
    useDebugValue(slice);
    return slice;
  }
  var createWithEqualityFnImpl = function createWithEqualityFnImpl(createState, defaultEqualityFn) {
    var api = vanilla.createStore(createState);
    var useBoundStoreWithEqualityFn = function useBoundStoreWithEqualityFn(selector, equalityFn) {
      if (equalityFn === void 0) {
        equalityFn = defaultEqualityFn;
      }
      return useStoreWithEqualityFn(api, selector, equalityFn);
    };
    Object.assign(useBoundStoreWithEqualityFn, api);
    return useBoundStoreWithEqualityFn;
  };
  var createWithEqualityFn = function createWithEqualityFn(createState, defaultEqualityFn) {
    return createState ? createWithEqualityFnImpl(createState, defaultEqualityFn) : createWithEqualityFnImpl;
  };

  exports.createWithEqualityFn = createWithEqualityFn;
  exports.useStoreWithEqualityFn = useStoreWithEqualityFn;

}));
