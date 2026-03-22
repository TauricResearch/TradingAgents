'use strict';

var ReactExports = require('react');
var traditional = require('zustand/traditional');

function _extends() {
  return _extends = Object.assign ? Object.assign.bind() : function (n) {
    for (var e = 1; e < arguments.length; e++) {
      var t = arguments[e];
      for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]);
    }
    return n;
  }, _extends.apply(null, arguments);
}

var createElement = ReactExports.createElement,
  reactCreateContext = ReactExports.createContext,
  useContext = ReactExports.useContext,
  useMemo = ReactExports.useMemo,
  useRef = ReactExports.useRef;
function createContext() {
  if (process.env.NODE_ENV !== 'production') {
    console.warn("[DEPRECATED] `context` will be removed in a future version. Instead use `import { createStore, useStore } from 'zustand'`. See: https://github.com/pmndrs/zustand/discussions/1180.");
  }
  var ZustandContext = reactCreateContext(undefined);
  var Provider = function Provider(_ref) {
    var createStore = _ref.createStore,
      children = _ref.children;
    var storeRef = useRef();
    if (!storeRef.current) {
      storeRef.current = createStore();
    }
    return createElement(ZustandContext.Provider, {
      value: storeRef.current
    }, children);
  };
  var useContextStore = function useContextStore(selector, equalityFn) {
    var store = useContext(ZustandContext);
    if (!store) {
      throw new Error('Seems like you have not used zustand provider as an ancestor.');
    }
    return traditional.useStoreWithEqualityFn(store, selector, equalityFn);
  };
  var useStoreApi = function useStoreApi() {
    var store = useContext(ZustandContext);
    if (!store) {
      throw new Error('Seems like you have not used zustand provider as an ancestor.');
    }
    return useMemo(function () {
      return _extends({}, store);
    }, [store]);
  };
  return {
    Provider: Provider,
    useStore: useContextStore,
    useStoreApi: useStoreApi
  };
}

module.exports = createContext;
