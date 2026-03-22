'use strict';

var vanilla = require('zustand/vanilla');
var ReactExports = require('react');
var useSyncExternalStoreExports = require('use-sync-external-store/shim/with-selector');

var useDebugValue = ReactExports.useDebugValue;
var useSyncExternalStoreWithSelector = useSyncExternalStoreExports.useSyncExternalStoreWithSelector;
var didWarnAboutEqualityFn = false;
var identity = function identity(arg) {
  return arg;
};
function useStore(api, selector, equalityFn) {
  if (selector === void 0) {
    selector = identity;
  }
  if (process.env.NODE_ENV !== 'production' && equalityFn && !didWarnAboutEqualityFn) {
    console.warn("[DEPRECATED] Use `createWithEqualityFn` instead of `create` or use `useStoreWithEqualityFn` instead of `useStore`. They can be imported from 'zustand/traditional'. https://github.com/pmndrs/zustand/discussions/1937");
    didWarnAboutEqualityFn = true;
  }
  var slice = useSyncExternalStoreWithSelector(api.subscribe, api.getState, api.getServerState || api.getInitialState, selector, equalityFn);
  useDebugValue(slice);
  return slice;
}
var createImpl = function createImpl(createState) {
  if (process.env.NODE_ENV !== 'production' && typeof createState !== 'function') {
    console.warn("[DEPRECATED] Passing a vanilla store will be unsupported in a future version. Instead use `import { useStore } from 'zustand'`.");
  }
  var api = typeof createState === 'function' ? vanilla.createStore(createState) : createState;
  var useBoundStore = function useBoundStore(selector, equalityFn) {
    return useStore(api, selector, equalityFn);
  };
  Object.assign(useBoundStore, api);
  return useBoundStore;
};
var create = function create(createState) {
  return createState ? createImpl(createState) : createImpl;
};
var react = (function (createState) {
  if (process.env.NODE_ENV !== 'production') {
    console.warn("[DEPRECATED] Default export is deprecated. Instead use `import { create } from 'zustand'`.");
  }
  return create(createState);
});

exports.create = create;
exports.default = react;
exports.useStore = useStore;
Object.keys(vanilla).forEach(function (k) {
  if (k !== 'default' && !Object.prototype.hasOwnProperty.call(exports, k)) Object.defineProperty(exports, k, {
    enumerable: true,
    get: function () { return vanilla[k]; }
  });
});

module.exports = react;
module.exports.create = create;
module.exports.useStore = useStore;
module.exports.createStore = vanilla.createStore;
exports.default = module.exports;
