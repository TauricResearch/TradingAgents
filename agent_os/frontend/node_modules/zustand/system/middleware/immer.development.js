System.register(['immer'], (function (exports) {
  'use strict';
  var produce;
  return {
    setters: [function (module) {
      produce = module.produce;
    }],
    execute: (function () {

      const immerImpl = (initializer) => (set, get, store) => {
        store.setState = (updater, replace, ...a) => {
          const nextState = typeof updater === "function" ? produce(updater) : updater;
          return set(nextState, replace, ...a);
        };
        return initializer(store.setState, get, store);
      };
      const immer = exports("immer", immerImpl);

    })
  };
}));
