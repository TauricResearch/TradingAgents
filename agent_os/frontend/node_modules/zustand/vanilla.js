'use strict';

var createStoreImpl = function createStoreImpl(createState) {
  var state;
  var listeners = new Set();
  var setState = function setState(partial, replace) {
    var nextState = typeof partial === 'function' ? partial(state) : partial;
    if (!Object.is(nextState, state)) {
      var _previousState = state;
      state = (replace != null ? replace : typeof nextState !== 'object' || nextState === null) ? nextState : Object.assign({}, state, nextState);
      listeners.forEach(function (listener) {
        return listener(state, _previousState);
      });
    }
  };
  var getState = function getState() {
    return state;
  };
  var getInitialState = function getInitialState() {
    return initialState;
  };
  var subscribe = function subscribe(listener) {
    listeners.add(listener);
    return function () {
      return listeners.delete(listener);
    };
  };
  var destroy = function destroy() {
    if (process.env.NODE_ENV !== 'production') {
      console.warn('[DEPRECATED] The `destroy` method will be unsupported in a future version. Instead use unsubscribe function returned by subscribe. Everything will be garbage-collected if store is garbage-collected.');
    }
    listeners.clear();
  };
  var api = {
    setState: setState,
    getState: getState,
    getInitialState: getInitialState,
    subscribe: subscribe,
    destroy: destroy
  };
  var initialState = state = createState(setState, getState, api);
  return api;
};
var createStore = function createStore(createState) {
  return createState ? createStoreImpl(createState) : createStoreImpl;
};
var vanilla = (function (createState) {
  if (process.env.NODE_ENV !== 'production') {
    console.warn("[DEPRECATED] Default export is deprecated. Instead use import { createStore } from 'zustand/vanilla'.");
  }
  return createStore(createState);
});

exports.createStore = createStore;
exports.default = vanilla;

module.exports = vanilla;
module.exports.createStore = createStore;
exports.default = module.exports;
