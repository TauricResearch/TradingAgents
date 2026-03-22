(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports, require('react')) :
  typeof define === 'function' && define.amd ? define(['exports', 'react'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.zustandReactShallow = {}, global.React));
})(this, (function (exports, ReactExports) { 'use strict';

  function _arrayLikeToArray(r, a) {
    (null == a || a > r.length) && (a = r.length);
    for (var e = 0, n = Array(a); e < a; e++) n[e] = r[e];
    return n;
  }
  function _createForOfIteratorHelperLoose(r, e) {
    var t = "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
    if (t) return (t = t.call(r)).next.bind(t);
    if (Array.isArray(r) || (t = _unsupportedIterableToArray(r)) || e) {
      t && (r = t);
      var o = 0;
      return function () {
        return o >= r.length ? {
          done: !0
        } : {
          done: !1,
          value: r[o++]
        };
      };
    }
    throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  function _unsupportedIterableToArray(r, a) {
    if (r) {
      if ("string" == typeof r) return _arrayLikeToArray(r, a);
      var t = {}.toString.call(r).slice(8, -1);
      return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0;
    }
  }

  function shallow(objA, objB) {
    if (Object.is(objA, objB)) {
      return true;
    }
    if (typeof objA !== 'object' || objA === null || typeof objB !== 'object' || objB === null) {
      return false;
    }
    if (objA instanceof Map && objB instanceof Map) {
      if (objA.size !== objB.size) return false;
      for (var _iterator = _createForOfIteratorHelperLoose(objA), _step; !(_step = _iterator()).done;) {
        var _step$value = _step.value,
          key = _step$value[0],
          value = _step$value[1];
        if (!Object.is(value, objB.get(key))) {
          return false;
        }
      }
      return true;
    }
    if (objA instanceof Set && objB instanceof Set) {
      if (objA.size !== objB.size) return false;
      for (var _iterator2 = _createForOfIteratorHelperLoose(objA), _step2; !(_step2 = _iterator2()).done;) {
        var _value = _step2.value;
        if (!objB.has(_value)) {
          return false;
        }
      }
      return true;
    }
    var keysA = Object.keys(objA);
    if (keysA.length !== Object.keys(objB).length) {
      return false;
    }
    for (var _i = 0, _keysA = keysA; _i < _keysA.length; _i++) {
      var keyA = _keysA[_i];
      if (!Object.prototype.hasOwnProperty.call(objB, keyA) || !Object.is(objA[keyA], objB[keyA])) {
        return false;
      }
    }
    return true;
  }

  var useRef = ReactExports.useRef;
  function useShallow(selector) {
    var prev = useRef();
    return function (state) {
      var next = selector(state);
      return shallow(prev.current, next) ? prev.current : prev.current = next;
    };
  }

  exports.useShallow = useShallow;

}));
