(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
  typeof define === 'function' && define.amd ? define(['exports'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.zustandMiddleware = {}));
})(this, (function (exports) { 'use strict';

  function _extends() {
    return _extends = Object.assign ? Object.assign.bind() : function (n) {
      for (var e = 1; e < arguments.length; e++) {
        var t = arguments[e];
        for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]);
      }
      return n;
    }, _extends.apply(null, arguments);
  }
  function _objectWithoutPropertiesLoose(r, e) {
    if (null == r) return {};
    var t = {};
    for (var n in r) if ({}.hasOwnProperty.call(r, n)) {
      if (e.includes(n)) continue;
      t[n] = r[n];
    }
    return t;
  }

  var reduxImpl = function reduxImpl(reducer, initial) {
    return function (set, _get, api) {
      api.dispatch = function (action) {
        set(function (state) {
          return reducer(state, action);
        }, false, action);
        return action;
      };
      api.dispatchFromDevtools = true;
      return _extends({
        dispatch: function dispatch() {
          var _ref;
          return (_ref = api).dispatch.apply(_ref, arguments);
        }
      }, initial);
    };
  };
  var redux = reduxImpl;

  var _excluded = ["enabled", "anonymousActionType", "store"],
    _excluded2 = ["connection"];
  var trackedConnections = new Map();
  var getTrackedConnectionState = function getTrackedConnectionState(name) {
    var api = trackedConnections.get(name);
    if (!api) return {};
    return Object.fromEntries(Object.entries(api.stores).map(function (_ref) {
      var key = _ref[0],
        api = _ref[1];
      return [key, api.getState()];
    }));
  };
  var extractConnectionInformation = function extractConnectionInformation(store, extensionConnector, options) {
    if (store === undefined) {
      return {
        type: 'untracked',
        connection: extensionConnector.connect(options)
      };
    }
    var existingConnection = trackedConnections.get(options.name);
    if (existingConnection) {
      return _extends({
        type: 'tracked',
        store: store
      }, existingConnection);
    }
    var newConnection = {
      connection: extensionConnector.connect(options),
      stores: {}
    };
    trackedConnections.set(options.name, newConnection);
    return _extends({
      type: 'tracked',
      store: store
    }, newConnection);
  };
  var devtoolsImpl = function devtoolsImpl(fn, devtoolsOptions) {
    if (devtoolsOptions === void 0) {
      devtoolsOptions = {};
    }
    return function (set, get, api) {
      var _devtoolsOptions = devtoolsOptions,
        enabled = _devtoolsOptions.enabled,
        anonymousActionType = _devtoolsOptions.anonymousActionType,
        store = _devtoolsOptions.store,
        options = _objectWithoutPropertiesLoose(_devtoolsOptions, _excluded);
      var extensionConnector;
      try {
        extensionConnector = (enabled != null ? enabled : "development" !== 'production') && window.__REDUX_DEVTOOLS_EXTENSION__;
      } catch (_e) {}
      if (!extensionConnector) {
        if (enabled) {
          console.warn('[zustand devtools middleware] Please install/enable Redux devtools extension');
        }
        return fn(set, get, api);
      }
      var _extractConnectionInf = extractConnectionInformation(store, extensionConnector, options),
        connection = _extractConnectionInf.connection,
        connectionInformation = _objectWithoutPropertiesLoose(_extractConnectionInf, _excluded2);
      var isRecording = true;
      api.setState = function (state, replace, nameOrAction) {
        var _extends2;
        var r = set(state, replace);
        if (!isRecording) return r;
        var action = nameOrAction === undefined ? {
          type: anonymousActionType || 'anonymous'
        } : typeof nameOrAction === 'string' ? {
          type: nameOrAction
        } : nameOrAction;
        if (store === undefined) {
          connection == null || connection.send(action, get());
          return r;
        }
        connection == null || connection.send(_extends({}, action, {
          type: store + "/" + action.type
        }), _extends({}, getTrackedConnectionState(options.name), (_extends2 = {}, _extends2[store] = api.getState(), _extends2)));
        return r;
      };
      var setStateFromDevtools = function setStateFromDevtools() {
        var originalIsRecording = isRecording;
        isRecording = false;
        set.apply(void 0, arguments);
        isRecording = originalIsRecording;
      };
      var initialState = fn(api.setState, get, api);
      if (connectionInformation.type === 'untracked') {
        connection == null || connection.init(initialState);
      } else {
        connectionInformation.stores[connectionInformation.store] = api;
        connection == null || connection.init(Object.fromEntries(Object.entries(connectionInformation.stores).map(function (_ref2) {
          var key = _ref2[0],
            store = _ref2[1];
          return [key, key === connectionInformation.store ? initialState : store.getState()];
        })));
      }
      if (api.dispatchFromDevtools && typeof api.dispatch === 'function') {
        var didWarnAboutReservedActionType = false;
        var originalDispatch = api.dispatch;
        api.dispatch = function () {
          for (var _len = arguments.length, a = new Array(_len), _key = 0; _key < _len; _key++) {
            a[_key] = arguments[_key];
          }
          if (a[0].type === '__setState' && !didWarnAboutReservedActionType) {
            console.warn('[zustand devtools middleware] "__setState" action type is reserved ' + 'to set state from the devtools. Avoid using it.');
            didWarnAboutReservedActionType = true;
          }
          originalDispatch.apply(void 0, a);
        };
      }
      connection.subscribe(function (message) {
        switch (message.type) {
          case 'ACTION':
            if (typeof message.payload !== 'string') {
              console.error('[zustand devtools middleware] Unsupported action format');
              return;
            }
            return parseJsonThen(message.payload, function (action) {
              if (action.type === '__setState') {
                if (store === undefined) {
                  setStateFromDevtools(action.state);
                  return;
                }
                if (Object.keys(action.state).length !== 1) {
                  console.error("\n                    [zustand devtools middleware] Unsupported __setState action format. \n                    When using 'store' option in devtools(), the 'state' should have only one key, which is a value of 'store' that was passed in devtools(),\n                    and value of this only key should be a state object. Example: { \"type\": \"__setState\", \"state\": { \"abc123Store\": { \"foo\": \"bar\" } } }\n                    ");
                }
                var stateFromDevtools = action.state[store];
                if (stateFromDevtools === undefined || stateFromDevtools === null) {
                  return;
                }
                if (JSON.stringify(api.getState()) !== JSON.stringify(stateFromDevtools)) {
                  setStateFromDevtools(stateFromDevtools);
                }
                return;
              }
              if (!api.dispatchFromDevtools) return;
              if (typeof api.dispatch !== 'function') return;
              api.dispatch(action);
            });
          case 'DISPATCH':
            switch (message.payload.type) {
              case 'RESET':
                setStateFromDevtools(initialState);
                if (store === undefined) {
                  return connection == null ? void 0 : connection.init(api.getState());
                }
                return connection == null ? void 0 : connection.init(getTrackedConnectionState(options.name));
              case 'COMMIT':
                if (store === undefined) {
                  connection == null || connection.init(api.getState());
                  return;
                }
                return connection == null ? void 0 : connection.init(getTrackedConnectionState(options.name));
              case 'ROLLBACK':
                return parseJsonThen(message.state, function (state) {
                  if (store === undefined) {
                    setStateFromDevtools(state);
                    connection == null || connection.init(api.getState());
                    return;
                  }
                  setStateFromDevtools(state[store]);
                  connection == null || connection.init(getTrackedConnectionState(options.name));
                });
              case 'JUMP_TO_STATE':
              case 'JUMP_TO_ACTION':
                return parseJsonThen(message.state, function (state) {
                  if (store === undefined) {
                    setStateFromDevtools(state);
                    return;
                  }
                  if (JSON.stringify(api.getState()) !== JSON.stringify(state[store])) {
                    setStateFromDevtools(state[store]);
                  }
                });
              case 'IMPORT_STATE':
                {
                  var _nextLiftedState$comp;
                  var nextLiftedState = message.payload.nextLiftedState;
                  var lastComputedState = (_nextLiftedState$comp = nextLiftedState.computedStates.slice(-1)[0]) == null ? void 0 : _nextLiftedState$comp.state;
                  if (!lastComputedState) return;
                  if (store === undefined) {
                    setStateFromDevtools(lastComputedState);
                  } else {
                    setStateFromDevtools(lastComputedState[store]);
                  }
                  connection == null || connection.send(null, nextLiftedState);
                  return;
                }
              case 'PAUSE_RECORDING':
                return isRecording = !isRecording;
            }
            return;
        }
      });
      return initialState;
    };
  };
  var devtools = devtoolsImpl;
  var parseJsonThen = function parseJsonThen(stringified, f) {
    var parsed;
    try {
      parsed = JSON.parse(stringified);
    } catch (e) {
      console.error('[zustand devtools middleware] Could not parse the received json', e);
    }
    if (parsed !== undefined) f(parsed);
  };

  var subscribeWithSelectorImpl = function subscribeWithSelectorImpl(fn) {
    return function (set, get, api) {
      var origSubscribe = api.subscribe;
      api.subscribe = function (selector, optListener, options) {
        var listener = selector;
        if (optListener) {
          var equalityFn = (options == null ? void 0 : options.equalityFn) || Object.is;
          var currentSlice = selector(api.getState());
          listener = function listener(state) {
            var nextSlice = selector(state);
            if (!equalityFn(currentSlice, nextSlice)) {
              var previousSlice = currentSlice;
              optListener(currentSlice = nextSlice, previousSlice);
            }
          };
          if (options != null && options.fireImmediately) {
            optListener(currentSlice, currentSlice);
          }
        }
        return origSubscribe(listener);
      };
      var initialState = fn(set, get, api);
      return initialState;
    };
  };
  var subscribeWithSelector = subscribeWithSelectorImpl;

  var combine = function combine(initialState, create) {
    return function () {
      return Object.assign({}, initialState, create.apply(void 0, arguments));
    };
  };

  function createJSONStorage(getStorage, options) {
    var storage;
    try {
      storage = getStorage();
    } catch (_e) {
      return;
    }
    var persistStorage = {
      getItem: function getItem(name) {
        var _getItem;
        var parse = function parse(str) {
          if (str === null) {
            return null;
          }
          return JSON.parse(str, options == null ? void 0 : options.reviver);
        };
        var str = (_getItem = storage.getItem(name)) != null ? _getItem : null;
        if (str instanceof Promise) {
          return str.then(parse);
        }
        return parse(str);
      },
      setItem: function setItem(name, newValue) {
        return storage.setItem(name, JSON.stringify(newValue, options == null ? void 0 : options.replacer));
      },
      removeItem: function removeItem(name) {
        return storage.removeItem(name);
      }
    };
    return persistStorage;
  }
  var _toThenable = function toThenable(fn) {
    return function (input) {
      try {
        var result = fn(input);
        if (result instanceof Promise) {
          return result;
        }
        return {
          then: function then(onFulfilled) {
            return _toThenable(onFulfilled)(result);
          },
          catch: function _catch(_onRejected) {
            return this;
          }
        };
      } catch (e) {
        return {
          then: function then(_onFulfilled) {
            return this;
          },
          catch: function _catch(onRejected) {
            return _toThenable(onRejected)(e);
          }
        };
      }
    };
  };
  var oldImpl = function oldImpl(config, baseOptions) {
    return function (set, get, api) {
      var options = _extends({
        getStorage: function getStorage() {
          return localStorage;
        },
        serialize: JSON.stringify,
        deserialize: JSON.parse,
        partialize: function partialize(state) {
          return state;
        },
        version: 0,
        merge: function merge(persistedState, currentState) {
          return _extends({}, currentState, persistedState);
        }
      }, baseOptions);
      var _hasHydrated = false;
      var hydrationListeners = new Set();
      var finishHydrationListeners = new Set();
      var storage;
      try {
        storage = options.getStorage();
      } catch (_e) {}
      if (!storage) {
        return config(function () {
          console.warn("[zustand persist middleware] Unable to update item '" + options.name + "', the given storage is currently unavailable.");
          set.apply(void 0, arguments);
        }, get, api);
      }
      var thenableSerialize = _toThenable(options.serialize);
      var setItem = function setItem() {
        var state = options.partialize(_extends({}, get()));
        var errorInSync;
        var thenable = thenableSerialize({
          state: state,
          version: options.version
        }).then(function (serializedValue) {
          return storage.setItem(options.name, serializedValue);
        }).catch(function (e) {
          errorInSync = e;
        });
        if (errorInSync) {
          throw errorInSync;
        }
        return thenable;
      };
      var savedSetState = api.setState;
      api.setState = function (state, replace) {
        savedSetState(state, replace);
        void setItem();
      };
      var configResult = config(function () {
        set.apply(void 0, arguments);
        void setItem();
      }, get, api);
      var stateFromStorage;
      var hydrate = function hydrate() {
        if (!storage) return;
        _hasHydrated = false;
        hydrationListeners.forEach(function (cb) {
          return cb(get());
        });
        var postRehydrationCallback = (options.onRehydrateStorage == null ? void 0 : options.onRehydrateStorage(get())) || undefined;
        return _toThenable(storage.getItem.bind(storage))(options.name).then(function (storageValue) {
          if (storageValue) {
            return options.deserialize(storageValue);
          }
        }).then(function (deserializedStorageValue) {
          if (deserializedStorageValue) {
            if (typeof deserializedStorageValue.version === 'number' && deserializedStorageValue.version !== options.version) {
              if (options.migrate) {
                return options.migrate(deserializedStorageValue.state, deserializedStorageValue.version);
              }
              console.error("State loaded from storage couldn't be migrated since no migrate function was provided");
            } else {
              return deserializedStorageValue.state;
            }
          }
        }).then(function (migratedState) {
          var _get;
          stateFromStorage = options.merge(migratedState, (_get = get()) != null ? _get : configResult);
          set(stateFromStorage, true);
          return setItem();
        }).then(function () {
          postRehydrationCallback == null || postRehydrationCallback(stateFromStorage, undefined);
          _hasHydrated = true;
          finishHydrationListeners.forEach(function (cb) {
            return cb(stateFromStorage);
          });
        }).catch(function (e) {
          postRehydrationCallback == null || postRehydrationCallback(undefined, e);
        });
      };
      api.persist = {
        setOptions: function setOptions(newOptions) {
          options = _extends({}, options, newOptions);
          if (newOptions.getStorage) {
            storage = newOptions.getStorage();
          }
        },
        clearStorage: function clearStorage() {
          var _storage;
          (_storage = storage) == null || _storage.removeItem(options.name);
        },
        getOptions: function getOptions() {
          return options;
        },
        rehydrate: function rehydrate() {
          return hydrate();
        },
        hasHydrated: function hasHydrated() {
          return _hasHydrated;
        },
        onHydrate: function onHydrate(cb) {
          hydrationListeners.add(cb);
          return function () {
            hydrationListeners.delete(cb);
          };
        },
        onFinishHydration: function onFinishHydration(cb) {
          finishHydrationListeners.add(cb);
          return function () {
            finishHydrationListeners.delete(cb);
          };
        }
      };
      hydrate();
      return stateFromStorage || configResult;
    };
  };
  var newImpl = function newImpl(config, baseOptions) {
    return function (set, get, api) {
      var options = _extends({
        storage: createJSONStorage(function () {
          return localStorage;
        }),
        partialize: function partialize(state) {
          return state;
        },
        version: 0,
        merge: function merge(persistedState, currentState) {
          return _extends({}, currentState, persistedState);
        }
      }, baseOptions);
      var _hasHydrated2 = false;
      var hydrationListeners = new Set();
      var finishHydrationListeners = new Set();
      var storage = options.storage;
      if (!storage) {
        return config(function () {
          console.warn("[zustand persist middleware] Unable to update item '" + options.name + "', the given storage is currently unavailable.");
          set.apply(void 0, arguments);
        }, get, api);
      }
      var setItem = function setItem() {
        var state = options.partialize(_extends({}, get()));
        return storage.setItem(options.name, {
          state: state,
          version: options.version
        });
      };
      var savedSetState = api.setState;
      api.setState = function (state, replace) {
        savedSetState(state, replace);
        void setItem();
      };
      var configResult = config(function () {
        set.apply(void 0, arguments);
        void setItem();
      }, get, api);
      api.getInitialState = function () {
        return configResult;
      };
      var stateFromStorage;
      var hydrate = function hydrate() {
        var _get3;
        if (!storage) return;
        _hasHydrated2 = false;
        hydrationListeners.forEach(function (cb) {
          var _get2;
          return cb((_get2 = get()) != null ? _get2 : configResult);
        });
        var postRehydrationCallback = (options.onRehydrateStorage == null ? void 0 : options.onRehydrateStorage((_get3 = get()) != null ? _get3 : configResult)) || undefined;
        return _toThenable(storage.getItem.bind(storage))(options.name).then(function (deserializedStorageValue) {
          if (deserializedStorageValue) {
            if (typeof deserializedStorageValue.version === 'number' && deserializedStorageValue.version !== options.version) {
              if (options.migrate) {
                return [true, options.migrate(deserializedStorageValue.state, deserializedStorageValue.version)];
              }
              console.error("State loaded from storage couldn't be migrated since no migrate function was provided");
            } else {
              return [false, deserializedStorageValue.state];
            }
          }
          return [false, undefined];
        }).then(function (migrationResult) {
          var _get4;
          var migrated = migrationResult[0],
            migratedState = migrationResult[1];
          stateFromStorage = options.merge(migratedState, (_get4 = get()) != null ? _get4 : configResult);
          set(stateFromStorage, true);
          if (migrated) {
            return setItem();
          }
        }).then(function () {
          postRehydrationCallback == null || postRehydrationCallback(stateFromStorage, undefined);
          stateFromStorage = get();
          _hasHydrated2 = true;
          finishHydrationListeners.forEach(function (cb) {
            return cb(stateFromStorage);
          });
        }).catch(function (e) {
          postRehydrationCallback == null || postRehydrationCallback(undefined, e);
        });
      };
      api.persist = {
        setOptions: function setOptions(newOptions) {
          options = _extends({}, options, newOptions);
          if (newOptions.storage) {
            storage = newOptions.storage;
          }
        },
        clearStorage: function clearStorage() {
          var _storage2;
          (_storage2 = storage) == null || _storage2.removeItem(options.name);
        },
        getOptions: function getOptions() {
          return options;
        },
        rehydrate: function rehydrate() {
          return hydrate();
        },
        hasHydrated: function hasHydrated() {
          return _hasHydrated2;
        },
        onHydrate: function onHydrate(cb) {
          hydrationListeners.add(cb);
          return function () {
            hydrationListeners.delete(cb);
          };
        },
        onFinishHydration: function onFinishHydration(cb) {
          finishHydrationListeners.add(cb);
          return function () {
            finishHydrationListeners.delete(cb);
          };
        }
      };
      if (!options.skipHydration) {
        hydrate();
      }
      return stateFromStorage || configResult;
    };
  };
  var persistImpl = function persistImpl(config, baseOptions) {
    if ('getStorage' in baseOptions || 'serialize' in baseOptions || 'deserialize' in baseOptions) {
      {
        console.warn('[DEPRECATED] `getStorage`, `serialize` and `deserialize` options are deprecated. Use `storage` option instead.');
      }
      return oldImpl(config, baseOptions);
    }
    return newImpl(config, baseOptions);
  };
  var persist = persistImpl;

  exports.combine = combine;
  exports.createJSONStorage = createJSONStorage;
  exports.devtools = devtools;
  exports.persist = persist;
  exports.redux = redux;
  exports.subscribeWithSelector = subscribeWithSelector;

}));
