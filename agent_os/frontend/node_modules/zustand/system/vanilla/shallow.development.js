System.register([], (function (exports) {
  'use strict';
  return {
    execute: (function () {

      exports("shallow", shallow);

      function shallow(objA, objB) {
        if (Object.is(objA, objB)) {
          return true;
        }
        if (typeof objA !== "object" || objA === null || typeof objB !== "object" || objB === null) {
          return false;
        }
        if (objA instanceof Map && objB instanceof Map) {
          if (objA.size !== objB.size) return false;
          for (const [key, value] of objA) {
            if (!Object.is(value, objB.get(key))) {
              return false;
            }
          }
          return true;
        }
        if (objA instanceof Set && objB instanceof Set) {
          if (objA.size !== objB.size) return false;
          for (const value of objA) {
            if (!objB.has(value)) {
              return false;
            }
          }
          return true;
        }
        const keysA = Object.keys(objA);
        if (keysA.length !== Object.keys(objB).length) {
          return false;
        }
        for (const keyA of keysA) {
          if (!Object.prototype.hasOwnProperty.call(objB, keyA) || !Object.is(objA[keyA], objB[keyA])) {
            return false;
          }
        }
        return true;
      }

    })
  };
}));
