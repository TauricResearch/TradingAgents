let weakMemoize = function <Arg extends object, Return>(
  func: (arg: Arg) => Return
): (arg: Arg) => Return {
  let cache = new WeakMap<Arg, Return>()
  return (arg: Arg) => {
    if (cache.has(arg)) {
      // Use non-null assertion because we just checked that the cache `has` it
      // This allows us to remove `undefined` from the return value
      return cache.get(arg)!
    }
    let ret = func(arg)
    cache.set(arg, ret)
    return ret
  }
}

export default weakMemoize
