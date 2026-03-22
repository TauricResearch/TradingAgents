(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports, require('immer')) :
  typeof define === 'function' && define.amd ? define(['exports', 'immer'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.zustandMiddlewareImmer = {}, global.immer));
})(this, (function (exports, immer$1) { 'use strict';

  var immerImpl = function immerImpl(initializer) {
    return function (set, get, store) {
      store.setState = function (updater, replace) {
        var nextState = typeof updater === 'function' ? immer$1.produce(updater) : updater;
        for (var _len = arguments.length, a = new Array(_len > 2 ? _len - 2 : 0), _key = 2; _key < _len; _key++) {
          a[_key - 2] = arguments[_key];
        }
        return set.apply(void 0, [nextState, replace].concat(a));
      };
      return initializer(store.setState, get, store);
    };
  };
  var immer = immerImpl;

  exports.immer = immer;

}));
